"""Domain types and formatting helpers for the storefront."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from src.uploads import image_thumb_url

STUDIO_TZ = ZoneInfo(os.environ.get("SHOP_TIMEZONE", "Europe/Nicosia"))


ORDER_STATUSES = ("new", "in_progress", "ready", "shipped", "cancelled")
ARCHIVABLE_STATUSES = ("shipped", "cancelled")
ORDER_STATUS_LABELS = {
    "new": "New",
    "in_progress": "In progress",
    "ready": "Ready to ship",
    "shipped": "Shipped",
    "cancelled": "Cancelled",
}
PAYMENT_STATUS_LABELS = {
    "unpaid": "Unpaid",
    "paid": "Paid",
    "refunded": "Refunded",
}

CYPRUS_SHIPPING_CENTS = 350
INTERNATIONAL_SHIPPING_CENTS = 1000
SHIPPING_METHODS = ("pickup", "delivery")
CHECKOUT_DELIVERY_COUNTRIES = ("cyprus", "greece")
DELIVERY_COUNTRIES = ("cyprus", "greece", "other")
COUNTRY_LABELS = {
    "cyprus": "Cyprus",
    "greece": "Greece",
    "other": "International",
}
PAYMENT_METHODS = ("card", "cash")
PICKUP_ADDRESS_LABEL = "Pick up at studio"


def normalize_payment_method(raw: str, shipping_method: str) -> str:
    """Card is the default. Cash is only valid with pick up at the studio."""
    method = (raw or "card").strip().lower()
    if method in ("", "card"):
        return "card"
    if method == "cash":
        if shipping_method != "pickup":
            raise ValueError("Cash is only available when you pick up at the studio")
        return "cash"
    raise ValueError("Choose card or cash at pick up")


def shipping_method_label(shipping_method: str, delivery_country: str | None = None) -> str:
    """Human-readable fulfillment method for admin, emails, and order pages."""
    if shipping_method == "pickup":
        return "Pick up at studio"
    if delivery_country == "greece":
        return "Delivery in Greece"
    if delivery_country == "other":
        return "International delivery"
    if shipping_method == "delivery":
        return "Delivery in Cyprus"
    return ""


PRODUCT_CODE_PREFIXES = {
    "Harry Potter": "HP",
    "Lord of the Rings": "LOTR",
    "Household": "HH",
    "Pokemon": "PK",
    "3D Prints": "3D",
    "Laser Engraving": "LC",
}


def product_code_prefix(category: str) -> str:
    return PRODUCT_CODE_PREFIXES.get(category, "PMM")


def normalize_product_code(raw: str | None) -> str:
    """Uppercase A–Z, digits, and hyphens, max 16 characters."""
    text = (raw or "").strip().upper()
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"[^A-Z0-9-]", "", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text[:16]


def format_money(cents: int) -> str:
    """Render integer cents as a euro string for templates."""
    return f"€{cents / 100:.2f}"


def clean_phone(raw: str) -> str:
    return " ".join((raw or "").split())[:40]


def phone_has_enough_digits(raw: str, minimum: int = 8) -> bool:
    digits = "".join(ch for ch in raw if ch.isdigit())
    return len(digits) >= minimum


def parse_studio_day(raw: str | None) -> str | None:
    """Return YYYY-MM-DD if raw is a calendar day, else None."""
    text = (raw or "").strip()
    if not text:
        return None
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return None
    return text


def studio_day_utc_bounds(day: str) -> tuple[str, str] | None:
    """Inclusive UTC start and exclusive UTC end for a Europe/Nicosia calendar day."""
    parsed = parse_studio_day(day)
    if not parsed:
        return None
    start_local = datetime.strptime(parsed, "%Y-%m-%d").replace(tzinfo=STUDIO_TZ)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    return (
        start_utc.strftime("%Y-%m-%d %H:%M:%S"),
        end_utc.strftime("%Y-%m-%d %H:%M:%S"),
    )


def format_local_time(raw: str) -> str:
    """Show UTC SQLite timestamps in the studio timezone (Europe/Nicosia)."""
    text = (raw or "").strip()
    if not text:
        return ""
    parsed: datetime | None = None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    local = parsed.astimezone(STUDIO_TZ)
    if local.hour == 0 and local.minute == 0 and len(text) == 10:
        return local.strftime("%Y-%m-%d")
    return local.strftime("%Y-%m-%d %H:%M")


def shipping_cents(shipping_method: str, delivery_country: str | None = None) -> int:
    """Shipping is chosen at checkout: pick-up is free; Cyprus €3.50; Greece (and legacy international) €10."""
    if shipping_method == "pickup":
        return 0
    if delivery_country in ("greece", "other"):
        return INTERNATIONAL_SHIPPING_CENTS
    return CYPRUS_SHIPPING_CENTS


def format_shipping_address(
    *,
    address_line: str = "",
    city: str = "",
    postal_code: str = "",
    delivery_country: str = "",
    fallback: str = "",
) -> str:
    """Join street, city, postcode, and country into one stored address block."""
    country_name = COUNTRY_LABELS.get((delivery_country or "").strip().lower(), "")
    parts = [
        (address_line or "").strip(),
        (city or "").strip(),
        (postal_code or "").strip(),
        country_name,
    ]
    composed = "\n".join(part for part in parts if part)
    if composed:
        return composed
    return (fallback or "").strip()


def order_total_cents(subtotal_cents: int, shipping_method: str, delivery_country: str | None = None) -> int:
    """Subtotal plus checkout shipping for order persistence."""
    return subtotal_cents + shipping_cents(shipping_method, delivery_country)


@dataclass(frozen=True)
class ProductImage:
    """One photo on a product listing."""

    id: int
    url: str
    sort_order: int = 0

    @property
    def thumb_url(self) -> str:
        return image_thumb_url(self.url)


@dataclass(frozen=True)
class Product:
    """A sellable item from the catalog."""

    id: int
    slug: str
    name: str
    description: str
    price_cents: int
    image_url: str
    category: str
    stock: int
    hidden: bool = False
    gallery: tuple[ProductImage, ...] = ()
    code: str = ""

    @classmethod
    def from_row(cls, row: Any, *, gallery: tuple[ProductImage, ...] = ()) -> "Product":
        keys = row.keys()
        hidden = bool(row["hidden"]) if "hidden" in keys and row["hidden"] else False
        photos = gallery
        cover = photos[0].url if photos else row["image_url"]
        return cls(
            id=row["id"],
            slug=row["slug"],
            name=row["name"],
            description=row["description"],
            price_cents=row["price_cents"],
            image_url=cover,
            category=row["category"],
            stock=row["stock"],
            hidden=hidden,
            gallery=photos,
            code=(row["code"] or "").strip() if "code" in keys and row["code"] else "",
        )

    @property
    def listed(self) -> bool:
        return not self.hidden

    @property
    def gallery_urls(self) -> list[str]:
        urls = [photo.url for photo in self.gallery]
        return urls if urls else [self.image_url]

    @property
    def thumb_url(self) -> str:
        return image_thumb_url(self.image_url)

    @property
    def price_display(self) -> str:
        return format_money(self.price_cents)


@dataclass(frozen=True)
class CartLine:
    """One product line in the session cart."""

    product: Product
    quantity: int

    @property
    def line_total_cents(self) -> int:
        return self.product.price_cents * self.quantity

    @property
    def line_total_display(self) -> str:
        return format_money(self.line_total_cents)


@dataclass(frozen=True)
class OrderItem:
    """One persisted line on a completed order."""

    product_name: str
    quantity: int
    unit_price_cents: int
    product_code: str = ""

    @property
    def studio_label(self) -> str:
        if self.product_code:
            return f"{self.product_code}  {self.product_name}"
        return self.product_name

    @property
    def line_total_cents(self) -> int:
        return self.unit_price_cents * self.quantity

    @property
    def line_total_display(self) -> str:
        return format_money(self.line_total_cents)


@dataclass(frozen=True)
class Order:
    """A placed order with line items for the confirmation page."""

    id: int
    customer_name: str
    customer_email: str
    shipping_address: str
    total_cents: int
    created_at: str
    items: list[OrderItem]
    status: str = "new"
    notes: str = ""
    lookup_token: str = ""
    payment_status: str = "unpaid"
    shipping_method: str = ""
    delivery_country: str = ""
    tracking_number: str = ""
    customer_notes: str = ""
    customer_phone: str = ""
    payment_method: str = ""
    archived: bool = False

    @property
    def paid(self) -> bool:
        return self.payment_status == "paid"

    @property
    def card_paid(self) -> bool:
        return self.paid and self.payment_method != "cash"

    @property
    def pay_at_pickup(self) -> bool:
        """Unpaid order the customer chose to settle in cash at the studio."""
        return self.payment_method == "cash" and not self.paid

    @property
    def created_at_display(self) -> str:
        return format_local_time(self.created_at)

    @property
    def created_at_day(self) -> str:
        display = self.created_at_display
        return display[:10] if display else ""

    @property
    def can_archive(self) -> bool:
        return self.status in ARCHIVABLE_STATUSES

    @property
    def customer_order_path(self) -> str:
        if self.lookup_token:
            return f"/order/{self.lookup_token}"
        return ""

    @property
    def payment_label(self) -> str:
        return PAYMENT_STATUS_LABELS.get(self.payment_status, self.payment_status)

    @property
    def shipping_label(self) -> str:
        return shipping_method_label(self.shipping_method, self.delivery_country or None)

    @property
    def status_label(self) -> str:
        return ORDER_STATUS_LABELS.get(self.status, self.status)

    @property
    def subtotal_cents(self) -> int:
        return sum(item.line_total_cents for item in self.items)

    @property
    def shipping_cents(self) -> int:
        return max(0, self.total_cents - self.subtotal_cents)

    @property
    def total_display(self) -> str:
        return format_money(self.total_cents)
