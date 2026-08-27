"""Turn a paid Stripe Checkout session into a shop order."""

from __future__ import annotations

import logging

from src.models import DELIVERY_COUNTRIES, PICKUP_ADDRESS_LABEL, SHIPPING_METHODS, Order
from src.notify import notify_payment_failure, schedule_order_email
from src.payments import refund_payment
from src.store import (
    get_order,
    get_pending_checkout,
    lines_from_cart_json,
    order_id_for_stripe_session,
    place_order,
)

logger = logging.getLogger(__name__)


class PaidCheckoutError(Exception):
    """Paid Stripe session could not be turned into an order."""


def complete_paid_session(session: dict) -> Order:
    """Idempotently create the order for a paid Checkout session."""
    session_id = str(session.get("id") or "").strip()
    if not session_id:
        raise PaidCheckoutError("Missing Stripe session id")

    existing_id = order_id_for_stripe_session(session_id)
    if existing_id:
        order = get_order(existing_id)
        if order:
            return order
        raise PaidCheckoutError("Mapped Stripe session has no order")

    pending = get_pending_checkout(session_id)
    meta = session.get("metadata") or {}
    if pending:
        lines = lines_from_cart_json(str(pending.get("cart_json") or ""))
        name = str(pending.get("customer_name") or "").strip() or "Customer"
        email = str(pending.get("customer_email") or "").strip()
        address = str(pending.get("shipping_address") or "").strip() or PICKUP_ADDRESS_LABEL
        method = str(pending.get("shipping_method") or "pickup").strip().lower()
        country = str(pending.get("delivery_country") or "").strip().lower()
        shipping = int(pending.get("shipping_cents") or 0)
        expected = int(pending.get("total_cents") or 0)
    else:
        lines = lines_from_cart_json(str(meta.get("cart") or ""))
        name = str(meta.get("customer_name") or "").strip() or "Customer"
        email = str(meta.get("customer_email") or "").strip()
        address = str(meta.get("shipping_address") or "").strip() or PICKUP_ADDRESS_LABEL
        method = str(meta.get("shipping_method") or "pickup").strip().lower()
        country = str(meta.get("delivery_country") or "").strip().lower()
        shipping = int(meta.get("shipping_cents") or 0)
        expected = int(meta.get("total_cents") or 0)

    if method not in SHIPPING_METHODS:
        method = "pickup"
    if method != "delivery":
        country = ""
    elif country not in DELIVERY_COUNTRIES:
        country = "cyprus"

    paid_amount = int(session.get("amount_total") or 0)
    if expected and paid_amount != expected:
        _fail_paid(session, email, f"Paid amount {paid_amount} does not match expected {expected}")
    if not lines:
        _fail_paid(session, email, "Could not rebuild the cart after payment")

    try:
        order_id = place_order(
            customer_name=name,
            customer_email=email,
            shipping_address=address,
            lines=lines,
            shipping_cents=shipping,
            shipping_method=method,
            delivery_country=country,
            paid=True,
            stripe_session_id=session_id,
        )
    except ValueError as exc:
        _fail_paid(session, email, str(exc))

    order = get_order(order_id)
    if not order:
        raise PaidCheckoutError("Order was not stored")
    schedule_order_email(order)
    return order


def _fail_paid(session: dict, customer_email: str, reason: str) -> None:
    refunded = False
    try:
        refund_payment(session)
        refunded = True
    except Exception:
        logger.exception("Refund failed for session %s", session.get("id"))
    notify_payment_failure(
        session_id=str(session.get("id") or ""),
        customer_email=customer_email,
        reason=reason,
        refunded=refunded,
    )
    raise PaidCheckoutError(reason)
