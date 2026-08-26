"""FastAPI storefront — catalog, cart, and checkout."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from src.admin import router as admin_router
from src.db import data_persistent, init_schema, product_images_dir
from src.models import (
    DELIVERY_COUNTRIES,
    PICKUP_ADDRESS_LABEL,
    SHIPPING_METHODS,
    format_money,
    shipping_cents,
)
from src.ratelimit import RateLimitMiddleware
from src.security import SecurityHeadersMiddleware, require_production_secrets, session_https_only, session_secret
from src.seed import seed_products
from src.notify import mail_configured, schedule_order_email
from src.payments import create_checkout_session, paid_session, payments_configured
from src.store import (
    build_cart_lines,
    cart_from_snapshot,
    cart_total_cents,
    get_order,
    get_order_by_token,
    get_product,
    get_product_by_slug,
    list_categories,
    list_products,
    order_id_for_stripe_session,
    place_order,
    remember_stripe_session,
)

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = session_secret()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Prepare database and demo catalog on container boot."""
    require_production_secrets()
    init_schema()
    seed_products()
    yield


app = FastAPI(title="Print Me Maybe", version="0.2.0", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=60 * 60 * 24 * 7, same_site="lax", https_only=session_https_only())
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["format_money"] = format_money
app.include_router(admin_router)


def get_cart(request: Request) -> dict[str, int]:
    """Session cart maps product id strings to quantities."""
    raw = request.session.get("cart", {})
    if not isinstance(raw, dict):
        return {}
    return {str(k): int(v) for k, v in raw.items() if int(v) > 0}


def save_cart(request: Request, cart: dict[str, int]) -> None:
    request.session["cart"] = {k: v for k, v in cart.items() if v > 0}


def cart_count(cart: dict[str, int]) -> int:
    return sum(cart.values())


def shop_name() -> str:
    return os.environ.get("SHOP_NAME", "Print Me Maybe")


def checkout_totals(
    lines: list,
    shipping_method: str = "pickup",
    delivery_country: str | None = "cyprus",
) -> dict[str, int]:
    """Shared subtotal, shipping, and total for cart and checkout views."""
    subtotal = cart_total_cents(lines)
    shipping = shipping_cents(shipping_method, delivery_country)
    return {
        "subtotal_cents": subtotal,
        "shipping_cents": shipping,
        "total_cents": subtotal + shipping,
        "shipping_method": shipping_method,
        "delivery_country": delivery_country,
    }


def normalize_shipping_method(raw: str) -> str:
    method = (raw or "").strip().lower()
    if method not in SHIPPING_METHODS:
        raise ValueError("Choose pick up or delivery")
    return method


def normalize_delivery_country(raw: str | None) -> str:
    country = (raw or "").strip().lower()
    if country not in DELIVERY_COUNTRIES:
        raise ValueError("Choose Cyprus or outside Cyprus for delivery")
    return country


@app.get("/health")
def health() -> dict[str, str | bool]:
    """Liveness plus whether THIS process can send mail (no secrets)."""
    return {
        "status": "ok",
        "service": "eshop",
        "mail": mail_configured(),
        "payments": payments_configured(),
        "persistent": data_persistent(),
    }


@app.get("/media/products/{filename}")
def serve_product_image(filename: str) -> FileResponse:
    """Serve a photo uploaded from the studio admin (stored under DATA_DIR)."""
    safe = Path(filename).name
    if not safe or safe != filename:
        raise HTTPException(status_code=404, detail="Not found")
    path = (product_images_dir() / safe).resolve()
    root = product_images_dir().resolve()
    if not path.is_file() or path.parent != root:
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(
        path,
        media_type=_image_media_type(safe),
        headers={"X-Content-Type-Options": "nosniff", "Content-Disposition": "inline"},
    )


def _image_media_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "application/octet-stream")


@app.get("/", response_class=HTMLResponse)
def home(request: Request, category: str | None = None) -> Any:
    cart = get_cart(request)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "products": list_products(category),
            "categories": list_categories(),
            "active_category": category,
            "cart_count": cart_count(cart),
            "shop_name": shop_name(),
        },
    )


@app.get("/product/{slug}", response_class=HTMLResponse)
def product_detail(request: Request, slug: str) -> Any:
    product = get_product_by_slug(slug)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    cart = get_cart(request)
    return templates.TemplateResponse(
        request,
        "product.html",
        {
            "product": product,
            "cart_count": cart_count(cart),
            "shop_name": shop_name(),
        },
    )


@app.post("/cart/add")
def cart_add(request: Request, product_id: int = Form(...), quantity: int = Form(1)) -> RedirectResponse:
    product = get_product(product_id)
    if not product or product.stock <= 0:
        return RedirectResponse(url="/", status_code=303)
    cart = get_cart(request)
    key = str(product_id)
    wanted = cart.get(key, 0) + max(1, min(quantity, 99))
    cart[key] = min(wanted, product.stock)
    save_cart(request, cart)
    return RedirectResponse(url="/cart", status_code=303)


@app.post("/cart/update")
def cart_update(request: Request, product_id: int = Form(...), quantity: int = Form(...)) -> RedirectResponse:
    cart = get_cart(request)
    key = str(product_id)
    if quantity <= 0:
        cart.pop(key, None)
    else:
        product = get_product(product_id)
        if not product or product.stock <= 0:
            cart.pop(key, None)
        else:
            cart[key] = min(max(quantity, 0), product.stock)
    save_cart(request, cart)
    return RedirectResponse(url="/cart", status_code=303)


@app.get("/cart", response_class=HTMLResponse)
def cart_page(request: Request) -> Any:
    cart = get_cart(request)
    lines = build_cart_lines(cart)
    totals = checkout_totals(lines, shipping_method="pickup")
    return templates.TemplateResponse(
        request,
        "cart.html",
        {
            "lines": lines,
            "cart_count": cart_count(cart),
            "shop_name": shop_name(),
            "subtotal_cents": totals["subtotal_cents"],
            "shipping_at_checkout": True,
        },
    )


@app.get("/checkout", response_class=HTMLResponse)
def checkout_page(request: Request) -> Any:
    cart = get_cart(request)
    lines = build_cart_lines(cart)
    if not lines:
        return RedirectResponse(url="/cart", status_code=303)

    totals = checkout_totals(lines)
    return templates.TemplateResponse(
        request,
        "checkout.html",
        {
            "lines": lines,
            "cart_count": cart_count(cart),
            "shop_name": shop_name(),
            "payments_on": payments_configured(),
            "international_shipping_display": format_money(
                shipping_cents("delivery", "other")
            ),
            "international_shipping_cents": shipping_cents("delivery", "other"),
            **totals,
        },
    )


@app.post("/checkout", response_class=HTMLResponse)
def checkout_submit(
    request: Request,
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    shipping_method: str = Form(...),
    delivery_country: str = Form("cyprus"),
    shipping_address: str = Form(""),
) -> Any:
    cart = get_cart(request)
    lines = build_cart_lines(cart)
    if not lines:
        return RedirectResponse(url="/cart", status_code=303)

    name = customer_name.strip()
    email = customer_email.strip()
    address = shipping_address.strip()

    checkout_ctx = {
        "lines": lines,
        "cart_count": cart_count(cart),
        "shop_name": shop_name(),
        "payments_on": payments_configured(),
        "international_shipping_display": format_money(shipping_cents("delivery", "other")),
        "international_shipping_cents": shipping_cents("delivery", "other"),
        "form_customer_name": name,
        "form_customer_email": email,
        "form_shipping_address": address,
    }

    try:
        method = normalize_shipping_method(shipping_method)
        country = normalize_delivery_country(delivery_country) if method == "delivery" else None
        if method == "delivery" and not address:
            raise ValueError("Enter a delivery address")
        if method == "pickup":
            address = PICKUP_ADDRESS_LABEL
        totals = checkout_totals(lines, shipping_method=method, delivery_country=country)
    except ValueError as exc:
        totals = checkout_totals(lines)
        return templates.TemplateResponse(
            request,
            "checkout.html",
            {
                **checkout_ctx,
                "error": str(exc),
                "form_shipping_method": shipping_method,
                "form_delivery_country": delivery_country,
                **totals,
            },
            status_code=400,
        )

    if payments_configured():
        try:
            pay_url = create_checkout_session(
                lines=lines,
                total_cents=totals["total_cents"],
                customer_name=name,
                customer_email=email,
                shipping_address=address,
                shipping_method=method,
                delivery_country=country or "",
                shipping_cents=totals["shipping_cents"],
                origin=str(request.base_url).rstrip("/"),
            )
        except Exception as exc:
            return templates.TemplateResponse(
                request,
                "checkout.html",
                {
                    **checkout_ctx,
                    "error": str(exc),
                    "form_shipping_method": method,
                    "form_delivery_country": country or delivery_country,
                    **totals,
                },
                status_code=400,
            )
        return RedirectResponse(url=pay_url, status_code=303)

    try:
        order_id = place_order(
            customer_name=name,
            customer_email=email,
            shipping_address=address,
            lines=lines,
            shipping_cents=totals["shipping_cents"],
        )
    except ValueError as exc:
        return templates.TemplateResponse(
            request,
            "checkout.html",
            {
                **checkout_ctx,
                "payments_on": False,
                "error": str(exc),
                "form_shipping_method": method,
                "form_delivery_country": country or delivery_country,
                **totals,
            },
            status_code=400,
        )

    save_cart(request, {})
    order = get_order(order_id)
    if order:
        schedule_order_email(order)
    return templates.TemplateResponse(
        request,
        "order_complete.html",
        {
            "order_id": order_id,
            "lookup_token": order.lookup_token if order else "",
            "cart_count": 0,
            "shop_name": shop_name(),
            "paid": False,
            **totals,
        },
    )


@app.get("/pay/success", response_class=HTMLResponse)
def pay_success(request: Request, session_id: str = "") -> Any:
    """Stripe returns here after a successful card payment."""
    if not payments_configured():
        return RedirectResponse(url="/checkout", status_code=303)
    existing = order_id_for_stripe_session(session_id)
    if existing:
        order = get_order(existing)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        totals = {
            "subtotal_cents": order.subtotal_cents,
            "shipping_cents": order.shipping_cents,
            "total_cents": order.total_cents,
        }
        return templates.TemplateResponse(
            request,
            "order_complete.html",
            {
                "order_id": order.id,
                "lookup_token": order.lookup_token,
                "cart_count": cart_count(get_cart(request)),
                "shop_name": shop_name(),
                "paid": True,
                **totals,
            },
        )
    try:
        session = paid_session(session_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not session:
        raise HTTPException(status_code=400, detail="Payment not completed")

    meta = session.get("metadata") or {}
    snapshot = str(meta.get("cart") or "")
    cart = cart_from_snapshot(snapshot) or get_cart(request)
    lines = build_cart_lines(cart)
    if not lines:
        raise HTTPException(
            status_code=400,
            detail="Could not rebuild the cart after payment. Contact the studio with your Stripe receipt.",
        )
    method = str(meta.get("shipping_method") or "pickup").strip().lower()
    if method not in SHIPPING_METHODS:
        method = "pickup"
    country_raw = str(meta.get("delivery_country") or "cyprus").strip().lower()
    country = country_raw if country_raw in DELIVERY_COUNTRIES else "cyprus"
    totals = checkout_totals(
        lines,
        shipping_method=method,
        delivery_country=country if method == "delivery" else None,
    )
    paid_amount = int(session.get("amount_total") or 0)
    expected = int(meta.get("total_cents") or totals["total_cents"])
    if paid_amount != expected:
        raise HTTPException(status_code=400, detail="Paid amount does not match the cart. Contact the studio.")

    try:
        order_id = place_order(
            customer_name=str(meta.get("customer_name") or "").strip() or "Customer",
            customer_email=str(meta.get("customer_email") or "").strip(),
            shipping_address=str(meta.get("shipping_address") or "").strip() or PICKUP_ADDRESS_LABEL,
            lines=lines,
            shipping_cents=totals["shipping_cents"],
            paid=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    remember_stripe_session(session_id, order_id)
    save_cart(request, {})
    order = get_order(order_id)
    if order:
        schedule_order_email(order)
    return templates.TemplateResponse(
        request,
        "order_complete.html",
        {
            "order_id": order_id,
            "lookup_token": order.lookup_token if order else "",
            "cart_count": 0,
            "shop_name": shop_name(),
            "paid": True,
            **totals,
        },
    )


@app.get("/order/{token}", response_class=HTMLResponse)
def order_detail(request: Request, token: str) -> Any:
    order = get_order_by_token(token)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    return templates.TemplateResponse(
        request,
        "order_detail.html",
        {
            "order": order,
            "cart_count": cart_count(get_cart(request)),
            "shop_name": shop_name(),
            "is_admin": False,
        },
    )


@app.get("/api/products")
def api_products() -> JSONResponse:
    """Lightweight JSON catalog for integrations or future SPA."""
    products = list_products()
    payload = [
        {
            "id": p.id,
            "slug": p.slug,
            "name": p.name,
            "price_cents": p.price_cents,
            "category": p.category,
            "image_url": p.image_url,
        }
        for p in products
    ]
    return JSONResponse(payload)
