"""Password-protected studio admin: orders and stock."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from src.models import (
    ORDER_STATUS_LABELS,
    ORDER_STATUSES,
    format_money,
)
from src.notify import (
    mail_configured,
    mail_domain_unverified_message,
    mail_not_configured_message,
    notify_order_cancelled,
    notify_order_shipped,
    record_failed_login,
    resend_from_needs_domain,
    send_test_email,
)
from src.payments import refund_order_if_paid
from src.ratelimit import client_ip
from src.store import (
    CATEGORIES,
    PLACEHOLDER_IMAGE,
    create_product,
    delete_product,
    euros_to_cents,
    get_order,
    get_product,
    list_all_products,
    list_orders,
    order_status_counts,
    set_payment_status,
    set_product_stock,
    stripe_session_id_for_order,
    unique_slug,
    update_order_notes,
    update_order_status,
    update_order_tracking,
    update_product,
)
from src.uploads import save_product_image

BASE_DIR = Path(__file__).resolve().parent.parent
router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["format_money"] = format_money
logger = logging.getLogger(__name__)


def shop_name() -> str:
    return os.environ.get("SHOP_NAME", "Print Me Maybe")


def admin_password() -> str:
    return os.environ.get("ADMIN_PASSWORD", "printmemaybe")


def is_admin(request: Request) -> bool:
    return bool(request.session.get("is_admin"))


def require_admin(request: Request) -> RedirectResponse | None:
    if is_admin(request):
        return None
    return RedirectResponse(url="/admin/login", status_code=303)


def _ctx(request: Request, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    data = {
        "shop_name": shop_name(),
        "cart_count": 0,
        "is_admin": True,
        "status_labels": ORDER_STATUS_LABELS,
        "statuses": ORDER_STATUSES,
    }
    if extra:
        data.update(extra)
    return data


@router.get("/login")
def login_page(request: Request) -> Any:
    if is_admin(request):
        return RedirectResponse(url="/admin/orders", status_code=303)
    return templates.TemplateResponse(
        request,
        "admin_login.html",
        {"shop_name": shop_name(), "cart_count": 0, "is_admin": False, "error": None},
    )


@router.post("/login")
def login_submit(request: Request, password: str = Form(...)) -> Any:
    expected = admin_password()
    given_digest = hashlib.sha256(password.encode("utf-8")).digest()
    expected_digest = hashlib.sha256(expected.encode("utf-8")).digest()
    if expected and hmac.compare_digest(given_digest, expected_digest):
        request.session["is_admin"] = True
        return RedirectResponse(url="/admin/orders", status_code=303)
    logger.warning("Failed admin login from %s", client_ip(request))
    record_failed_login(client_ip(request))
    return templates.TemplateResponse(
        request,
        "admin_login.html",
        {
            "shop_name": shop_name(),
            "cart_count": 0,
            "is_admin": False,
            "error": "Wrong password.",
        },
        status_code=401,
    )


@router.post("/logout")
def logout(request: Request) -> RedirectResponse:
    request.session.pop("is_admin", None)
    return RedirectResponse(url="/admin/login", status_code=303)


@router.get("")
def admin_home(request: Request) -> RedirectResponse:
    gate = require_admin(request)
    if gate:
        return gate
    return RedirectResponse(url="/admin/orders", status_code=303)


@router.get("/orders")
def orders_page(request: Request, status: str | None = None) -> Any:
    gate = require_admin(request)
    if gate:
        return gate
    if status and status not in ORDER_STATUSES:
        status = None
    return templates.TemplateResponse(
        request,
        "admin_orders.html",
        _ctx(
            request,
            {
                "orders": list_orders(status),
                "counts": order_status_counts(),
                "active_status": status,
                "notify_email": os.environ.get("NOTIFY_EMAIL", "dimitrioupanagiotis@outlook.com"),
                "mail_ready": mail_configured(),
                "mail_needs_domain": resend_from_needs_domain(),
                "mail_setup_hint": mail_not_configured_message(),
                "mail_domain_hint": mail_domain_unverified_message(),
            },
        ),
    )


@router.post("/test-email")
def test_email(request: Request) -> Any:
    gate = require_admin(request)
    if gate:
        return gate
    ok, message = send_test_email()
    return templates.TemplateResponse(
        request,
        "admin_orders.html",
        _ctx(
            request,
            {
                "orders": list_orders(),
                "counts": order_status_counts(),
                "active_status": None,
                "mail_ok": ok,
                "mail_status": message,
                "notify_email": os.environ.get("NOTIFY_EMAIL", "dimitrioupanagiotis@outlook.com"),
                "mail_ready": mail_configured(),
                "mail_needs_domain": resend_from_needs_domain(),
                "mail_setup_hint": mail_not_configured_message(),
                "mail_domain_hint": mail_domain_unverified_message(),
            },
        ),
        status_code=200 if ok else 400,
    )


@router.get("/orders/{order_id}")
def order_page(request: Request, order_id: int) -> Any:
    gate = require_admin(request)
    if gate:
        return gate
    order = get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return templates.TemplateResponse(
        request,
        "admin_order.html",
        _ctx(request, {"order": order}),
    )


@router.post("/orders/{order_id}")
def order_update(
    request: Request,
    order_id: int,
    status: str = Form(...),
    notes: str = Form(""),
    tracking_number: str = Form(""),
) -> Any:
    gate = require_admin(request)
    if gate:
        return gate
    if status not in ORDER_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    order = get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    def error_page(message: str, status_code: int = 400):
        current = get_order(order_id) or order
        return templates.TemplateResponse(
            request,
            "admin_order.html",
            _ctx(request, {"order": current, "error": message}),
            status_code=status_code,
        )

    cancelling = status == "cancelled" and order.status != "cancelled"
    refunded = order.payment_status == "refunded"
    if cancelling:
        try:
            did_refund = refund_order_if_paid(
                payment_status=order.payment_status,
                session_id=stripe_session_id_for_order(order_id),
            )
        except RuntimeError as exc:
            return error_page(str(exc))
        if did_refund:
            set_payment_status(order_id, "refunded")
            refunded = True
    try:
        update_order_status(order_id, status)
    except ValueError as exc:
        return error_page(str(exc))
    update_order_notes(order_id, notes.strip())
    saved_tracking = update_order_tracking(order_id, tracking_number)
    updated = get_order(order_id)
    if cancelling:
        if updated:
            notify_order_cancelled(updated, refunded=refunded)
    elif updated and status == "shipped":
        became_shipped = order.status != "shipped"
        tracking_changed = saved_tracking != (order.tracking_number or "").strip()
        if became_shipped or (saved_tracking and tracking_changed):
            notify_order_shipped(updated)
    return RedirectResponse(url=f"/admin/orders/{order_id}", status_code=303)


@router.get("/stock")
def stock_page(request: Request) -> Any:
    gate = require_admin(request)
    if gate:
        return gate
    return templates.TemplateResponse(
        request,
        "admin_stock.html",
        _ctx(
            request,
            {
                "products": list_all_products(),
                "categories": CATEGORIES,
                "error": None,
            },
        ),
    )


@router.post("/products")
def product_create(
    request: Request,
    name: str = Form(...),
    description: str = Form(...),
    price: str = Form(...),
    category: str = Form(...),
    stock: int = Form(0),
    image: UploadFile | None = File(None),
) -> Any:
    gate = require_admin(request)
    if gate:
        return gate

    def error_page(message: str, status_code: int = 400):
        return templates.TemplateResponse(
            request,
            "admin_stock.html",
            _ctx(
                request,
                {
                    "products": list_all_products(),
                    "categories": CATEGORIES,
                    "error": message,
                    "form_name": name,
                    "form_description": description,
                    "form_price": price,
                    "form_category": category,
                    "form_stock": stock,
                },
            ),
            status_code=status_code,
        )

    try:
        price_cents = euros_to_cents(price)
        slug = unique_slug(name)
        image_url = PLACEHOLDER_IMAGE
        if image is not None and image.filename:
            image_url = save_product_image(slug, image)
        create_product(
            name=name,
            description=description,
            price_cents=price_cents,
            category=category,
            stock=stock,
            image_url=image_url,
            slug=slug,
        )
    except ValueError as exc:
        return error_page(str(exc))

    return RedirectResponse(url="/admin/stock", status_code=303)


@router.get("/products/{product_id}/edit")
def product_edit_page(request: Request, product_id: int) -> Any:
    gate = require_admin(request)
    if gate:
        return gate
    product = get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return templates.TemplateResponse(
        request,
        "admin_product_edit.html",
        _ctx(
            request,
            {
                "product": product,
                "categories": CATEGORIES,
                "error": None,
                "form_name": product.name,
                "form_description": product.description,
                "form_price": f"{product.price_cents / 100:.2f}",
                "form_category": product.category,
                "form_stock": product.stock,
            },
        ),
    )


@router.post("/products/{product_id}/edit")
def product_edit_submit(
    request: Request,
    product_id: int,
    name: str = Form(...),
    description: str = Form(...),
    price: str = Form(...),
    category: str = Form(...),
    stock: int = Form(0),
    image: UploadFile | None = File(None),
) -> Any:
    gate = require_admin(request)
    if gate:
        return gate
    product = get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    def error_page(message: str, status_code: int = 400):
        return templates.TemplateResponse(
            request,
            "admin_product_edit.html",
            _ctx(
                request,
                {
                    "product": product,
                    "categories": CATEGORIES,
                    "error": message,
                    "form_name": name,
                    "form_description": description,
                    "form_price": price,
                    "form_category": category,
                    "form_stock": stock,
                },
            ),
            status_code=status_code,
        )

    try:
        price_cents = euros_to_cents(price)
        image_url = None
        if image is not None and image.filename:
            image_url = save_product_image(product.slug, image)
        update_product(
            product_id,
            name=name,
            description=description,
            price_cents=price_cents,
            category=category,
            stock=stock,
            image_url=image_url,
        )
    except ValueError as exc:
        return error_page(str(exc))

    return RedirectResponse(url="/admin/stock", status_code=303)


@router.post("/stock/{product_id}")
def stock_update(
    request: Request,
    product_id: int,
    stock: int = Form(...),
) -> RedirectResponse:
    gate = require_admin(request)
    if gate:
        return gate
    set_product_stock(product_id, stock)
    return RedirectResponse(url="/admin/stock", status_code=303)


@router.post("/products/{product_id}/delete")
def product_delete(request: Request, product_id: int) -> Any:
    gate = require_admin(request)
    if gate:
        return gate
    try:
        delete_product(product_id)
    except ValueError as exc:
        return templates.TemplateResponse(
            request,
            "admin_stock.html",
            _ctx(
                request,
                {
                    "products": list_all_products(),
                    "categories": CATEGORIES,
                    "error": str(exc),
                },
            ),
            status_code=400,
        )
    return RedirectResponse(url="/admin/stock", status_code=303)
