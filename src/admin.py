"""Password-protected studio admin: orders and stock."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

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
    notify_new_order,
    notify_order_cancelled,
    notify_order_ready,
    notify_order_shipped,
    record_failed_login,
    resend_from_needs_domain,
    send_test_email,
    should_email_shipped,
)
from src.payments import refund_order_if_paid
from src.ratelimit import client_ip
from src.store import (
    CATEGORIES,
    PLACEHOLDER_IMAGE,
    add_product_photos,
    catalog_counts,
    create_product,
    delete_product,
    delete_product_photo,
    euros_to_cents,
    get_order,
    get_product,
    list_all_products,
    list_orders,
    mark_order_paid_cash,
    order_shipping_counts,
    order_status_counts,
    set_payment_status,
    set_product_cover,
    set_product_hidden,
    set_product_stock,
    stripe_session_id_for_order,
    unique_slug,
    update_order_notes,
    update_order_status,
    update_order_tracking,
    update_product,
)
from src.uploads import save_product_images

BASE_DIR = Path(__file__).resolve().parent.parent
router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["format_money"] = format_money
logger = logging.getLogger(__name__)

SHIPPING_FILTERS = ("pickup", "cyprus", "other")
SHIPPING_FILTER_LABELS = {
    "pickup": "Pickup",
    "cyprus": "Cyprus delivery",
    "other": "Outside Cyprus",
}
MAIL_BANNERS = {
    "sent": ("ok", "Customer email sent."),
    "failed": ("error", "Order saved, but the email failed. Send it manually or use Resend."),
    "skipped": ("error", "Order saved. Email was skipped — set RESEND_API_KEY in /etc/eshop.env."),
    "need_tracking": (
        "error",
        "Order marked shipped. Add a tracking number to email the customer.",
    ),
}


def public_origin(request: Request) -> str:
    return (os.environ.get("SHOP_URL") or str(request.base_url)).rstrip("/")


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


def _orders_href(
    *,
    status: str | None = None,
    shipping: str | None = None,
    q: str | None = None,
) -> str:
    params: dict[str, str] = {}
    if status:
        params["status"] = status
    if shipping:
        params["shipping"] = shipping
    needle = (q or "").strip()
    if needle:
        params["q"] = needle
    qs = urlencode(params)
    return "/admin/orders?" + qs if qs else "/admin/orders"


def _mail_result(ok: bool) -> str:
    if ok:
        return "sent"
    return "skipped" if not mail_configured() else "failed"


def _order_redirect(order_id: int, mail: str | None = None) -> RedirectResponse:
    url = f"/admin/orders/{order_id}"
    if mail:
        url += "?" + urlencode({"mail": mail})
    return RedirectResponse(url=url, status_code=303)


def _order_view_extra(request: Request, order, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    origin = public_origin(request)
    customer_url = f"{origin}{order.customer_order_path}" if order.customer_order_path else ""
    data: dict[str, Any] = {
        "order": order,
        "stripe_session_id": stripe_session_id_for_order(order.id),
        "customer_order_url": customer_url,
        "mail_kind": None,
        "mail_status": None,
    }
    if extra:
        data.update(extra)
    mail = data.get("mail")
    banner = MAIL_BANNERS.get(mail or "")
    if banner:
        data["mail_kind"] = banner[0]
        data["mail_status"] = banner[1]
    return data


def _orders_list_extra(
    request: Request,
    *,
    status: str | None,
    shipping: str | None,
    q: str | None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if status and status not in ORDER_STATUSES:
        status = None
    if shipping and shipping not in SHIPPING_FILTERS:
        shipping = None
    needle = (q or "").strip()
    data: dict[str, Any] = {
        "orders": list_orders(status, shipping=shipping, q=needle),
        "counts": order_status_counts(),
        "shipping_counts": order_shipping_counts(),
        "shipping_labels": SHIPPING_FILTER_LABELS,
        "shipping_filters": SHIPPING_FILTERS,
        "active_status": status,
        "active_shipping": shipping,
        "search_q": needle,
        "clear_search_href": _orders_href(status=status, shipping=shipping, q=None),
        "all_href": _orders_href(status=None, shipping=shipping, q=needle),
        "status_hrefs": {
            key: _orders_href(status=key, shipping=shipping, q=needle) for key in ORDER_STATUSES
        },
        "shipping_all_href": _orders_href(status=status, shipping=None, q=needle),
        "shipping_hrefs": {
            key: _orders_href(status=status, shipping=key, q=needle) for key in SHIPPING_FILTERS
        },
        "notify_email": os.environ.get("NOTIFY_EMAIL", "dimitrioupanagiotis@outlook.com"),
        "mail_ready": mail_configured(),
        "mail_needs_domain": resend_from_needs_domain(),
        "mail_setup_hint": mail_not_configured_message(),
        "mail_domain_hint": mail_domain_unverified_message(),
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
def orders_page(
    request: Request,
    status: str | None = None,
    shipping: str | None = None,
    q: str | None = None,
) -> Any:
    gate = require_admin(request)
    if gate:
        return gate
    return templates.TemplateResponse(
        request,
        "admin_orders.html",
        _ctx(request, _orders_list_extra(request, status=status, shipping=shipping, q=q)),
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
            _orders_list_extra(
                request,
                status=None,
                shipping=None,
                q=None,
                extra={"mail_ok": ok, "mail_status": message},
            ),
        ),
        status_code=200 if ok else 400,
    )


@router.get("/orders/{order_id}")
def order_page(request: Request, order_id: int, mail: str | None = None) -> Any:
    gate = require_admin(request)
    if gate:
        return gate
    order = get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return templates.TemplateResponse(
        request,
        "admin_order.html",
        _ctx(request, _order_view_extra(request, order, {"mail": mail})),
    )


@router.get("/orders/{order_id}/print")
def order_print(request: Request, order_id: int) -> Any:
    gate = require_admin(request)
    if gate:
        return gate
    order = get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return templates.TemplateResponse(
        request,
        "admin_order_print.html",
        _ctx(request, _order_view_extra(request, order)),
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
            _ctx(request, _order_view_extra(request, current, {"error": message})),
            status_code=status_code,
        )

    cancelling = status == "cancelled" and order.status != "cancelled"
    did_refund = False
    if cancelling:
        try:
            did_refund = refund_order_if_paid(
                payment_status=order.payment_status,
                session_id=stripe_session_id_for_order(order_id),
                payment_method=order.payment_method,
            )
        except RuntimeError as exc:
            return error_page(str(exc))
        if did_refund:
            set_payment_status(order_id, "refunded")
    try:
        update_order_status(order_id, status)
    except ValueError as exc:
        return error_page(str(exc))
    update_order_notes(order_id, notes.strip())
    saved_tracking = update_order_tracking(order_id, tracking_number)
    updated = get_order(order_id)

    mail: str | None = None
    if cancelling:
        if updated:
            ok = notify_order_cancelled(updated, refunded=did_refund)
            mail = _mail_result(ok)
    elif updated and status == "ready" and order.status != "ready":
        ok = notify_order_ready(updated)
        mail = _mail_result(ok)
    elif updated and status == "shipped":
        became_shipped = order.status != "shipped"
        tracking_changed = saved_tracking != (order.tracking_number or "").strip()
        if became_shipped or (saved_tracking and tracking_changed):
            if should_email_shipped(updated):
                ok = notify_order_shipped(updated)
                mail = _mail_result(ok)
            else:
                mail = "need_tracking"
    return _order_redirect(order_id, mail)


@router.post("/orders/{order_id}/mark-paid")
def order_mark_paid(request: Request, order_id: int) -> Any:
    gate = require_admin(request)
    if gate:
        return gate
    order = get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        mark_order_paid_cash(order_id)
    except ValueError as exc:
        return templates.TemplateResponse(
            request,
            "admin_order.html",
            _ctx(request, _order_view_extra(request, order, {"error": str(exc)})),
            status_code=400,
        )
    return _order_redirect(order_id)


@router.post("/orders/{order_id}/resend")
def order_resend_confirmation(request: Request, order_id: int) -> Any:
    gate = require_admin(request)
    if gate:
        return gate
    order = get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    ok = notify_new_order(order)
    return _order_redirect(order_id, _mail_result(ok))


@router.post("/orders/{order_id}/resend-shipped")
def order_resend_shipped(request: Request, order_id: int) -> Any:
    gate = require_admin(request)
    if gate:
        return gate
    order = get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if not should_email_shipped(order):
        return _order_redirect(order_id, "need_tracking")
    ok = notify_order_shipped(order)
    return _order_redirect(order_id, _mail_result(ok))


@router.get("/stock")
def stock_page(
    request: Request,
    category: str | None = None,
    q: str | None = None,
    visibility: str | None = None,
    added: str | None = None,
) -> Any:
    gate = require_admin(request)
    if gate:
        return gate
    if visibility not in {None, "listed", "hidden"}:
        visibility = None
    if category and category not in CATEGORIES:
        category = None
    needle = (q or "").strip()
    return templates.TemplateResponse(
        request,
        "admin_stock.html",
        _ctx(
            request,
            {
                "products": list_all_products(category=category, q=needle, visibility=visibility),
                "categories": CATEGORIES,
                "catalog_counts": catalog_counts(),
                "active_category": category,
                "active_visibility": visibility,
                "search_q": needle,
                "added": bool(added),
                "error": None,
            },
        ),
    )


def _product_form_ctx(
    *,
    error: str | None = None,
    form_name: str = "",
    form_description: str = "",
    form_price: str = "",
    form_category: str = "",
    form_stock: int = 1,
    product=None,
) -> dict[str, Any]:
    return {
        "categories": CATEGORIES,
        "error": error,
        "form_name": form_name,
        "form_description": form_description,
        "form_price": form_price,
        "form_category": form_category,
        "form_stock": form_stock,
        "product": product,
    }


def _upload_list(*groups: list[UploadFile] | UploadFile | None) -> list[UploadFile]:
    files: list[UploadFile] = []
    for group in groups:
        if group is None:
            continue
        if isinstance(group, list):
            files.extend(group)
        else:
            files.append(group)
    return [item for item in files if getattr(item, "filename", None)]


@router.get("/products/new")
def product_new_page(request: Request) -> Any:
    gate = require_admin(request)
    if gate:
        return gate
    return templates.TemplateResponse(
        request,
        "admin_product_new.html",
        _ctx(request, _product_form_ctx()),
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
    images: list[UploadFile] | None = File(None),
) -> Any:
    gate = require_admin(request)
    if gate:
        return gate

    def error_page(message: str, status_code: int = 400):
        return templates.TemplateResponse(
            request,
            "admin_product_new.html",
            _ctx(
                request,
                _product_form_ctx(
                    error=message,
                    form_name=name,
                    form_description=description,
                    form_price=price,
                    form_category=category,
                    form_stock=stock,
                ),
            ),
            status_code=status_code,
        )

    try:
        price_cents = euros_to_cents(price)
        slug = unique_slug(name)
        urls = save_product_images(slug, _upload_list(image, images))
        create_product(
            name=name,
            description=description,
            price_cents=price_cents,
            category=category,
            stock=stock,
            image_url=urls[0] if urls else PLACEHOLDER_IMAGE,
            slug=slug,
            extra_image_urls=urls[1:],
        )
    except ValueError as exc:
        return error_page(str(exc))

    return RedirectResponse(url="/admin/stock?added=1", status_code=303)


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
            _product_form_ctx(
                product=product,
                form_name=product.name,
                form_description=product.description,
                form_price=f"{product.price_cents / 100:.2f}",
                form_category=product.category,
                form_stock=product.stock,
            ),
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
    images: list[UploadFile] | None = File(None),
) -> Any:
    gate = require_admin(request)
    if gate:
        return gate
    product = get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    def error_page(message: str, status_code: int = 400):
        current = get_product(product_id) or product
        return templates.TemplateResponse(
            request,
            "admin_product_edit.html",
            _ctx(
                request,
                _product_form_ctx(
                    error=message,
                    product=current,
                    form_name=name,
                    form_description=description,
                    form_price=price,
                    form_category=category,
                    form_stock=stock,
                ),
            ),
            status_code=status_code,
        )

    try:
        price_cents = euros_to_cents(price)
        update_product(
            product_id,
            name=name,
            description=description,
            price_cents=price_cents,
            category=category,
            stock=stock,
        )
        urls = save_product_images(product.slug, _upload_list(image, images))
        if urls:
            add_product_photos(product_id, urls)
    except ValueError as exc:
        return error_page(str(exc))

    return RedirectResponse(url=f"/admin/products/{product_id}/edit", status_code=303)


@router.post("/products/{product_id}/images/{image_id}/cover")
def product_image_cover(request: Request, product_id: int, image_id: int) -> Any:
    gate = require_admin(request)
    if gate:
        return gate
    try:
        set_product_cover(product_id, image_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url=f"/admin/products/{product_id}/edit", status_code=303)


@router.post("/products/{product_id}/images/{image_id}/delete")
def product_image_delete(request: Request, product_id: int, image_id: int) -> Any:
    gate = require_admin(request)
    if gate:
        return gate
    try:
        delete_product_photo(product_id, image_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url=f"/admin/products/{product_id}/edit", status_code=303)


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


@router.post("/products/{product_id}/hide")
def product_hide(request: Request, product_id: int) -> RedirectResponse:
    gate = require_admin(request)
    if gate:
        return gate
    set_product_hidden(product_id, True)
    return RedirectResponse(url="/admin/stock", status_code=303)


@router.post("/products/{product_id}/show")
def product_show(request: Request, product_id: int) -> RedirectResponse:
    gate = require_admin(request)
    if gate:
        return gate
    set_product_hidden(product_id, False)
    return RedirectResponse(url="/admin/stock", status_code=303)


@router.post("/products/{product_id}/delete")
def product_delete(request: Request, product_id: int) -> Any:
    gate = require_admin(request)
    if gate:
        return gate
    product = get_product(product_id)
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
                    "catalog_counts": catalog_counts(),
                    "active_category": None,
                    "active_visibility": None,
                    "search_q": "",
                    "added": False,
                    "error": str(exc),
                    "hide_instead": product,
                },
            ),
            status_code=400,
        )
    return RedirectResponse(url="/admin/stock", status_code=303)

