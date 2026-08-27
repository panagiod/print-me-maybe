"""Product catalog and order persistence."""

from __future__ import annotations

import json
import re
import secrets
import unicodedata
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from src.db import get_connection
from src.models import (
    ARCHIVABLE_STATUSES,
    CartLine,
    Genre,
    Order,
    OrderItem,
    Product,
    ProductImage,
    normalize_genre_name,
    normalize_genre_prefix,
    normalize_product_code,
    parse_studio_day,
    product_code_prefix,
    studio_day_utc_bounds,
)

PLACEHOLDER_IMAGE = "/static/images/products/placeholder.svg"
DEFAULT_HOME_TITLE = "Personalized 3D prints,\nmade to order."
DEFAULT_HOME_BANNER = (
    "Baby gifts, keepsakes, fandom décor, household pieces, and toys from "
    "@print.me.maybe — Harry Potter, Lord of the Rings, household, Pokémon, "
    "and toys. Made in Cyprus. Free pick up; €3.50 delivery in Cyprus; "
    "€10 delivery in Greece."
)
HOME_TITLE_MAX = 120
HOME_BANNER_MAX = 800
HOME_EYEBROW_MAX = 40
DEFAULT_HOME_EYEBROW = "Print Me Maybe"
_GENRE_SELECT = """
    SELECT g.id, g.name, g.code_prefix, g.sort_order,
           (SELECT COUNT(*) FROM products p WHERE p.category = g.name) AS product_count
    FROM product_genres g
"""


def slugify(name: str) -> str:
    """URL slug from a product name."""
    ascii_name = unicodedata.normalize("NFKD", name.strip()).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return slug or "item"


def euros_to_cents(raw: str) -> int:
    """Parse a euro amount typed in the admin form."""
    cleaned = raw.strip().replace("€", "").replace(" ", "").replace(",", ".")
    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("Enter a price like 15 or 15.00") from exc
    if value <= 0:
        raise ValueError("Price must be greater than zero")
    cents = int((value * 100).quantize(Decimal("1")))
    if cents <= 0:
        raise ValueError("Price must be greater than zero")
    return cents


def unique_slug(name: str) -> str:
    """Return a slug that is not already in the products table."""
    base = slugify(name)
    with get_connection() as conn:
        candidate = base
        suffix = 2
        while conn.execute("SELECT 1 FROM products WHERE slug = ?", (candidate,)).fetchone():
            candidate = f"{base}-{suffix}"
            suffix += 1
    return candidate


def ensure_shop_settings() -> None:
    """Insert default home copy only when those keys are missing. Never overwrite."""
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO shop_settings (key, value) VALUES ('home_title', ?)",
            (DEFAULT_HOME_TITLE,),
        )
        conn.execute(
            "INSERT OR IGNORE INTO shop_settings (key, value) VALUES ('home_banner', ?)",
            (DEFAULT_HOME_BANNER,),
        )
        conn.execute(
            "INSERT OR IGNORE INTO shop_settings (key, value) VALUES ('home_eyebrow', ?)",
            (DEFAULT_HOME_EYEBROW,),
        )


def get_home_copy() -> tuple[str, str, str]:
    """Home page eyebrow, title, and banner from SQLite."""
    with get_connection() as conn:
        title_row = conn.execute(
            "SELECT value FROM shop_settings WHERE key = 'home_title'"
        ).fetchone()
        banner_row = conn.execute(
            "SELECT value FROM shop_settings WHERE key = 'home_banner'"
        ).fetchone()
        eyebrow_row = conn.execute(
            "SELECT value FROM shop_settings WHERE key = 'home_eyebrow'"
        ).fetchone()
    title = (title_row["value"] if title_row else DEFAULT_HOME_TITLE).strip()
    banner = (banner_row["value"] if banner_row else DEFAULT_HOME_BANNER).strip()
    eyebrow = (eyebrow_row["value"] if eyebrow_row else DEFAULT_HOME_EYEBROW).strip()
    return (
        title or DEFAULT_HOME_TITLE,
        banner or DEFAULT_HOME_BANNER,
        eyebrow or DEFAULT_HOME_EYEBROW,
    )


def save_home_copy(*, title: str, banner: str, eyebrow: str = "") -> None:
    """Save studio edits to home copy. Survives restart and deploy."""
    cleaned_title = title.replace("\r\n", "\n").strip()
    cleaned_banner = banner.replace("\r\n", "\n").strip()
    cleaned_eyebrow = eyebrow.replace("\r\n", "\n").strip()
    if not cleaned_title:
        raise ValueError("Title is required")
    if not cleaned_banner:
        raise ValueError("Banner text is required")
    if not cleaned_eyebrow:
        _title, _banner, cleaned_eyebrow = get_home_copy()
    if len(cleaned_title) > HOME_TITLE_MAX:
        raise ValueError(f"Title must be {HOME_TITLE_MAX} characters or fewer")
    if len(cleaned_banner) > HOME_BANNER_MAX:
        raise ValueError(f"Banner must be {HOME_BANNER_MAX} characters or fewer")
    if len(cleaned_eyebrow) > HOME_EYEBROW_MAX:
        raise ValueError(f"Eyebrow must be {HOME_EYEBROW_MAX} characters or fewer")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO shop_settings (key, value) VALUES ('home_title', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (cleaned_title,),
        )
        conn.execute(
            """
            INSERT INTO shop_settings (key, value) VALUES ('home_banner', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (cleaned_banner,),
        )
        conn.execute(
            """
            INSERT INTO shop_settings (key, value) VALUES ('home_eyebrow', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (cleaned_eyebrow,),
        )


def list_products(category: str | None = None, q: str | None = None) -> list[Product]:
    """Return listed, in-stock products, optionally filtered by category or search."""
    query = "SELECT * FROM products WHERE stock > 0 AND COALESCE(hidden, 0) = 0"
    params: list[object] = []
    if category:
        query += " AND category = ?"
        params.append(category)
    needle = (q or "").strip()
    if needle:
        query += " AND (name LIKE ? OR description LIKE ? OR COALESCE(code, '') LIKE ?)"
        like = f"%{needle}%"
        params.extend([like, like, like])
    query += " ORDER BY category, name"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        return _products_from_rows(conn, rows)


def list_genres() -> list[Genre]:
    """Studio and shop genre chips, in sort order."""
    with get_connection() as conn:
        rows = conn.execute(_GENRE_SELECT + " ORDER BY g.sort_order, g.name").fetchall()
        return [Genre.from_row(row) for row in rows]


def list_categories() -> list[str]:
    """Genre names for shop chips and product forms."""
    return [genre.name for genre in list_genres()]


def get_genre(genre_id: int) -> Genre | None:
    with get_connection() as conn:
        row = conn.execute(_GENRE_SELECT + " WHERE g.id = ?", (genre_id,)).fetchone()
        return Genre.from_row(row) if row else None


def _canonical_genre_name(conn, category: str) -> str:
    cleaned = (category or "").strip()
    if not cleaned:
        raise ValueError("Genre is required")
    row = conn.execute(
        "SELECT name FROM product_genres WHERE name = ? COLLATE NOCASE",
        (cleaned,),
    ).fetchone()
    if not row:
        raise ValueError("Choose a genre")
    return row["name"]


def _genre_prefix(conn, category: str) -> str:
    row = conn.execute(
        "SELECT code_prefix FROM product_genres WHERE name = ? COLLATE NOCASE",
        ((category or "").strip(),),
    ).fetchone()
    if row and row["code_prefix"]:
        return row["code_prefix"]
    return product_code_prefix(category)


def _assert_genre_unique(conn, *, name: str, prefix: str, exclude_id: int | None = None) -> None:
    name_row = conn.execute(
        "SELECT id FROM product_genres WHERE name = ? COLLATE NOCASE",
        (name,),
    ).fetchone()
    if name_row and int(name_row["id"]) != exclude_id:
        raise ValueError("That genre already exists")
    prefix_row = conn.execute(
        "SELECT id FROM product_genres WHERE code_prefix = ? COLLATE NOCASE",
        (prefix,),
    ).fetchone()
    if prefix_row and int(prefix_row["id"]) != exclude_id:
        raise ValueError(f"Prefix {prefix} is already used")


def create_genre(*, name: str, code_prefix: str) -> Genre:
    cleaned = normalize_genre_name(name)
    prefix = normalize_genre_prefix(code_prefix)
    if not cleaned:
        raise ValueError("Genre name is required")
    if len(prefix) < 2:
        raise ValueError("Code prefix needs at least two letters")
    with get_connection() as conn:
        _assert_genre_unique(conn, name=cleaned, prefix=prefix)
        sort_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 10 FROM product_genres"
        ).fetchone()[0]
        cursor = conn.execute(
            "INSERT INTO product_genres (name, code_prefix, sort_order) VALUES (?, ?, ?)",
            (cleaned, prefix, sort_order),
        )
        row = conn.execute(_GENRE_SELECT + " WHERE g.id = ?", (cursor.lastrowid,)).fetchone()
        return Genre.from_row(row)


def update_genre(genre_id: int, *, name: str, code_prefix: str) -> Genre:
    existing = get_genre(genre_id)
    if not existing:
        raise ValueError("Genre not found")
    cleaned = normalize_genre_name(name)
    prefix = normalize_genre_prefix(code_prefix)
    if not cleaned:
        raise ValueError("Genre name is required")
    if len(prefix) < 2:
        raise ValueError("Code prefix needs at least two letters")
    with get_connection() as conn:
        _assert_genre_unique(conn, name=cleaned, prefix=prefix, exclude_id=genre_id)
        conn.execute(
            "UPDATE product_genres SET name = ?, code_prefix = ? WHERE id = ?",
            (cleaned, prefix, genre_id),
        )
        if cleaned != existing.name:
            conn.execute(
                "UPDATE products SET category = ? WHERE category = ?",
                (cleaned, existing.name),
            )
        row = conn.execute(_GENRE_SELECT + " WHERE g.id = ?", (genre_id,)).fetchone()
        return Genre.from_row(row)


def delete_genre(genre_id: int, *, move_to_id: int | None = None) -> None:
    existing = get_genre(genre_id)
    if not existing:
        raise ValueError("Genre not found")
    with get_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM products WHERE category = ?",
            (existing.name,),
        ).fetchone()[0]
        if count:
            if not move_to_id or int(move_to_id) == genre_id:
                raise ValueError(
                    f"Move the {count} product{'s' if count != 1 else ''} to another genre first"
                )
            dest = conn.execute(
                "SELECT name FROM product_genres WHERE id = ?",
                (move_to_id,),
            ).fetchone()
            if not dest:
                raise ValueError("Choose a genre to move products into")
            conn.execute(
                "UPDATE products SET category = ? WHERE category = ?",
                (dest["name"], existing.name),
            )
        conn.execute("DELETE FROM product_genres WHERE id = ?", (genre_id,))


def get_product(product_id: int) -> Product | None:
    """Look up a product by id for cart updates."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        return _product_from_row(conn, row) if row else None


def get_product_by_slug(slug: str) -> Product | None:
    """Look up a single product for the detail page."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM products WHERE slug = ?", (slug,)).fetchone()
        return _product_from_row(conn, row) if row else None


def get_products_by_ids(product_ids: Iterable[int]) -> dict[int, Product]:
    """Batch fetch products for cart rendering."""
    ids = list(product_ids)
    if not ids:
        return {}

    placeholders = ",".join("?" for _ in ids)
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM products WHERE id IN ({placeholders})",
            ids,
        ).fetchall()
        products = _products_from_rows(conn, rows)
    return {product.id: product for product in products}


def build_cart_lines(cart: dict[str, int]) -> list[CartLine]:
    """Turn session cart {product_id: qty} into display lines."""
    if not cart:
        return []

    products = get_products_by_ids(int(pid) for pid in cart)
    lines: list[CartLine] = []
    for pid_str, qty in cart.items():
        product = products.get(int(pid_str))
        if product and qty > 0 and not product.hidden:
            lines.append(CartLine(product=product, quantity=min(qty, product.stock)))
    return lines


def cart_total_cents(lines: list[CartLine]) -> int:
    """Sum line totals for checkout subtotal."""
    return sum(line.line_total_cents for line in lines)


def get_order(order_id: int) -> Order | None:
    """Fetch a placed order and its line items by studio id."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not row:
            return None
        return _order_from_row(conn, row)


def get_order_by_token(token: str) -> Order | None:
    """Fetch an order by the unguessable customer lookup token."""
    cleaned = (token or "").strip()
    if len(cleaned) < 16:
        return None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM orders WHERE lookup_token = ?",
            (cleaned,),
        ).fetchone()
        if not row:
            return None
        return _order_from_row(conn, row)


def list_all_products(
    *,
    category: str | None = None,
    q: str | None = None,
    visibility: str | None = None,
) -> list[Product]:
    """Admin catalog including sold-out and hidden items."""
    query = "SELECT * FROM products"
    clauses: list[str] = []
    params: list[object] = []
    if category:
        clauses.append("category = ?")
        params.append(category)
    needle = (q or "").strip()
    if needle:
        clauses.append("(name LIKE ? OR code LIKE ?)")
        like = f"%{needle}%"
        params.extend([like, like])
    if visibility == "hidden":
        clauses.append("COALESCE(hidden, 0) = 1")
    elif visibility == "listed":
        clauses.append("COALESCE(hidden, 0) = 0")
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += (
        " ORDER BY COALESCE(hidden, 0), CASE WHEN stock <= 0 THEN 1 ELSE 0 END, category, name"
    )
    with get_connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
        return _products_from_rows(conn, rows)


def catalog_counts() -> dict[str, int]:
    """Counts for admin listed / hidden chips."""
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        hidden = conn.execute(
            "SELECT COUNT(*) FROM products WHERE COALESCE(hidden, 0) = 1"
        ).fetchone()[0]
    return {"all": int(total), "listed": int(total) - int(hidden), "hidden": int(hidden)}


def set_product_stock(product_id: int, stock: int) -> None:
    """Set remaining stock from the admin stock page."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE products SET stock = ? WHERE id = ?",
            (max(0, stock), product_id),
        )


def set_product_hidden(product_id: int, hidden: bool) -> None:
    """Hide or show a product on the public shop without deleting it."""
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM products WHERE id = ?", (product_id,)).fetchone()
        if not row:
            raise ValueError("Product not found")
        conn.execute(
            "UPDATE products SET hidden = ? WHERE id = ?",
            (1 if hidden else 0, product_id),
        )


def delete_product(product_id: int) -> None:
    """Remove a product from the catalog. Fails if it appears on a past order."""
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM products WHERE id = ?", (product_id,)).fetchone()
        if not row:
            raise ValueError("Product not found")
        ordered = conn.execute(
            "SELECT 1 FROM order_items WHERE product_id = ? LIMIT 1",
            (product_id,),
        ).fetchone()
        if ordered:
            raise ValueError(
                "This product has been ordered before, so it cannot be deleted. "
                "Hide it from the shop instead."
            )
        conn.execute("DELETE FROM product_images WHERE product_id = ?", (product_id,))
        conn.execute("DELETE FROM products WHERE id = ?", (product_id,))


def _code_taken(conn, code: str, exclude_id: int | None = None) -> bool:
    if exclude_id is None:
        row = conn.execute("SELECT id FROM products WHERE code = ?", (code,)).fetchone()
    else:
        row = conn.execute(
            "SELECT id FROM products WHERE code = ? AND id != ?",
            (code, exclude_id),
        ).fetchone()
    return row is not None


def allocate_product_code(
    conn,
    *,
    category: str,
    product_id: int,
    requested: str = "",
    exclude_id: int | None = None,
) -> str:
    """Return a unique product code, or raise if the typed code is already used."""
    wanted = normalize_product_code(requested)
    if wanted:
        if not _code_taken(conn, wanted, exclude_id):
            return wanted
        raise ValueError(f"Product code {wanted} is already in use")
    prefix = _genre_prefix(conn, category)
    base = f"{prefix}-{product_id:03d}"
    if not _code_taken(conn, base, exclude_id):
        return base
    for extra in range(2, 100):
        candidate = f"{base}-{extra}"
        if not _code_taken(conn, candidate, exclude_id):
            return candidate
    raise ValueError("Could not allocate a product code")


def create_product(
    *,
    name: str,
    description: str,
    price_cents: int,
    category: str,
    stock: int,
    image_url: str,
    slug: str | None = None,
    extra_image_urls: list[str] | None = None,
    code: str = "",
) -> Product:
    """Insert a product created from the studio admin."""
    cleaned_name = name.strip()
    if not cleaned_name:
        raise ValueError("Name is required")
    cleaned_description = description.strip()
    if not cleaned_description:
        raise ValueError("Description is required")
    cleaned_category = category.strip()
    if not cleaned_category:
        raise ValueError("Genre is required")
    if price_cents <= 0:
        raise ValueError("Price must be greater than zero")

    product_slug = (slug or "").strip() or unique_slug(cleaned_name)
    photos = [image_url.strip()] if image_url.strip() else []
    for url in extra_image_urls or []:
        cleaned = (url or "").strip()
        if cleaned and cleaned not in photos:
            photos.append(cleaned)
    cover = photos[0] if photos else PLACEHOLDER_IMAGE
    qty = max(0, stock)

    with get_connection() as conn:
        cleaned_category = _canonical_genre_name(conn, cleaned_category)
        cursor = conn.execute(
            """
            INSERT INTO products (slug, name, description, price_cents, image_url, category, stock, hidden, code)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, '')
            """,
            (product_slug, cleaned_name, cleaned_description, price_cents, cover, cleaned_category, qty),
        )
        product_id = int(cursor.lastrowid)
        allocated = allocate_product_code(
            conn,
            category=cleaned_category,
            product_id=product_id,
            requested=code,
        )
        conn.execute("UPDATE products SET code = ? WHERE id = ?", (allocated, product_id))
        for index, url in enumerate(photos):
            if url and url != PLACEHOLDER_IMAGE:
                conn.execute(
                    "INSERT INTO product_images (product_id, url, sort_order) VALUES (?, ?, ?)",
                    (product_id, url, index),
                )
        _sync_cover(conn, product_id)
        row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        return _product_from_row(conn, row)


def update_product(
    product_id: int,
    *,
    name: str,
    description: str,
    price_cents: int,
    category: str,
    stock: int,
    image_url: str | None = None,
    code: str | None = None,
) -> Product:
    """Update listing fields from the studio edit form. Slug stays the same."""
    existing = get_product(product_id)
    if not existing:
        raise ValueError("Product not found")
    cleaned_name = name.strip()
    if not cleaned_name:
        raise ValueError("Name is required")
    cleaned_description = description.strip()
    if not cleaned_description:
        raise ValueError("Description is required")
    cleaned_category = category.strip()
    if not cleaned_category:
        raise ValueError("Genre is required")
    if price_cents <= 0:
        raise ValueError("Price must be greater than zero")
    photo = existing.image_url
    qty = max(0, stock)
    requested_code = existing.code if code is None else code

    with get_connection() as conn:
        cleaned_category = _canonical_genre_name(conn, cleaned_category)
        allocated = allocate_product_code(
            conn,
            category=cleaned_category,
            product_id=product_id,
            requested=requested_code,
            exclude_id=product_id,
        )
        conn.execute(
            """
            UPDATE products
            SET name = ?, description = ?, price_cents = ?, category = ?, stock = ?, code = ?
            WHERE id = ?
            """,
            (
                cleaned_name,
                cleaned_description,
                price_cents,
                cleaned_category,
                qty,
                allocated,
                product_id,
            ),
        )
        if image_url and image_url.strip() and image_url.strip() != PLACEHOLDER_IMAGE:
            _append_product_photos(conn, product_id, [image_url.strip()])
            _sync_cover(conn, product_id)
        row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        return _product_from_row(conn, row)


def add_product_photos(product_id: int, urls: list[str]) -> Product:
    """Append photos to a product gallery. The first existing photo stays the cover."""
    existing = get_product(product_id)
    if not existing:
        raise ValueError("Product not found")
    cleaned = [url.strip() for url in urls if (url or "").strip()]
    if not cleaned:
        return existing
    with get_connection() as conn:
        _append_product_photos(conn, product_id, cleaned)
        _sync_cover(conn, product_id)
        row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        return _product_from_row(conn, row)


def set_product_cover(product_id: int, image_id: int) -> None:
    """Make an existing gallery photo the cover (first in sort order)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM product_images WHERE id = ? AND product_id = ?",
            (image_id, product_id),
        ).fetchone()
        if not row:
            raise ValueError("Photo not found")
        conn.execute(
            "UPDATE product_images SET sort_order = sort_order + 1 WHERE product_id = ?",
            (product_id,),
        )
        conn.execute("UPDATE product_images SET sort_order = 0 WHERE id = ?", (image_id,))
        _sync_cover(conn, product_id)


def delete_product_photo(product_id: int, image_id: int) -> None:
    """Remove one gallery photo. Last photo falls back to the placeholder."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM product_images WHERE id = ? AND product_id = ?",
            (image_id, product_id),
        ).fetchone()
        if not row:
            raise ValueError("Photo not found")
        conn.execute(
            "DELETE FROM product_images WHERE id = ? AND product_id = ?",
            (image_id, product_id),
        )
        remaining = conn.execute(
            """
            SELECT url FROM product_images
            WHERE product_id = ?
            ORDER BY sort_order, id
            LIMIT 1
            """,
            (product_id,),
        ).fetchone()
        cover = remaining["url"] if remaining else PLACEHOLDER_IMAGE
        conn.execute("UPDATE products SET image_url = ? WHERE id = ?", (cover, product_id))


def _append_product_photos(conn, product_id: int, urls: list[str]) -> None:
    max_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), -1) FROM product_images WHERE product_id = ?",
        (product_id,),
    ).fetchone()[0]
    for index, url in enumerate(urls):
        conn.execute(
            "INSERT INTO product_images (product_id, url, sort_order) VALUES (?, ?, ?)",
            (product_id, url, int(max_order) + 1 + index),
        )


def _sync_cover(conn, product_id: int) -> None:
    row = conn.execute(
        """
        SELECT url FROM product_images
        WHERE product_id = ?
        ORDER BY sort_order, id
        LIMIT 1
        """,
        (product_id,),
    ).fetchone()
    cover = row["url"] if row else PLACEHOLDER_IMAGE
    conn.execute("UPDATE products SET image_url = ? WHERE id = ?", (cover, product_id))


def _gallery_for(conn, product_id: int) -> tuple[ProductImage, ...]:
    rows = conn.execute(
        """
        SELECT id, url, sort_order FROM product_images
        WHERE product_id = ?
        ORDER BY sort_order, id
        """,
        (product_id,),
    ).fetchall()
    return tuple(
        ProductImage(id=row["id"], url=row["url"], sort_order=row["sort_order"]) for row in rows
    )


def _product_from_row(conn, row) -> Product:
    return Product.from_row(row, gallery=_gallery_for(conn, row["id"]))


def _products_from_rows(conn, rows) -> list[Product]:
    ids = [row["id"] for row in rows]
    by_pid: dict[int, list[ProductImage]] = {product_id: [] for product_id in ids}
    if ids:
        placeholders = ",".join("?" for _ in ids)
        images = conn.execute(
            f"""
            SELECT id, product_id, url, sort_order FROM product_images
            WHERE product_id IN ({placeholders})
            ORDER BY sort_order, id
            """,
            ids,
        ).fetchall()
        for image in images:
            by_pid.setdefault(image["product_id"], []).append(
                ProductImage(id=image["id"], url=image["url"], sort_order=image["sort_order"])
            )
    return [
        Product.from_row(row, gallery=tuple(by_pid.get(row["id"], []))) for row in rows
    ]


def list_orders(
    status: str | None = None,
    *,
    shipping: str | None = None,
    q: str | None = None,
    archived: bool = False,
    date_from: str | None = None,
    date_to: str | None = None,
    sort: str = "newest",
) -> list[Order]:
    """Studio order list. Inbox (default) hides archived shipped/cancelled orders."""
    where, params = _order_filter_sql(
        status=status,
        shipping=shipping,
        q=q,
        archived=archived,
        date_from=date_from,
        date_to=date_to,
    )
    order_by = "ORDER BY created_at ASC, id ASC" if sort == "oldest" else "ORDER BY created_at DESC, id DESC"
    query = f"SELECT * FROM orders{where} {order_by}"
    with get_connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
        return [_order_from_row(conn, row) for row in rows]


def _order_filter_sql(
    *,
    status: str | None = None,
    shipping: str | None = None,
    q: str | None = None,
    archived: bool = False,
    date_from: str | None = None,
    date_to: str | None = None,
    include_archive_clause: bool = True,
) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if include_archive_clause:
        if archived:
            clauses.append("COALESCE(archived, 0) = 1")
        else:
            clauses.append("COALESCE(archived, 0) = 0")
    if status:
        clauses.append("status = ?")
        params.append(status)
    if shipping == "pickup":
        clauses.append("shipping_method = 'pickup'")
    elif shipping == "cyprus":
        clauses.append("shipping_method = 'delivery' AND delivery_country = 'cyprus'")
    elif shipping == "greece":
        clauses.append("shipping_method = 'delivery' AND delivery_country = 'greece'")
    elif shipping == "other":
        clauses.append("shipping_method = 'delivery' AND delivery_country = 'other'")
    needle = (q or "").strip()
    if needle:
        if needle.isdigit():
            clauses.append(
                "(id = ? OR customer_name LIKE ? OR customer_email LIKE ? OR tracking_number LIKE ?"
                " OR id IN (SELECT order_id FROM order_items WHERE product_code LIKE ? OR product_name LIKE ?))"
            )
            like = f"%{needle}%"
            params.extend([int(needle), like, like, like, like, like])
        else:
            clauses.append(
                "(customer_name LIKE ? OR customer_email LIKE ? OR tracking_number LIKE ?"
                " OR id IN (SELECT order_id FROM order_items WHERE product_code LIKE ? OR product_name LIKE ?))"
            )
            like = f"%{needle}%"
            params.extend([like, like, like, like, like])
    start_day = parse_studio_day(date_from)
    end_day = parse_studio_day(date_to)
    if start_day:
        bounds = studio_day_utc_bounds(start_day)
        if bounds:
            clauses.append("created_at >= ?")
            params.append(bounds[0])
    if end_day:
        bounds = studio_day_utc_bounds(end_day)
        if bounds:
            clauses.append("created_at < ?")
            params.append(bounds[1])
    if not clauses:
        return "", []
    return " WHERE " + " AND ".join(clauses), params


def order_shipping_counts(
    *,
    archived: bool = False,
    q: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    status: str | None = None,
) -> dict[str, int]:
    """Counts for pickup vs Cyprus vs Greece vs legacy-international filter chips."""
    base, params = _order_filter_sql(
        status=status,
        q=q,
        archived=archived,
        date_from=date_from,
        date_to=date_to,
    )
    joiner = " AND " if base else " WHERE "
    with get_connection() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM orders{base}", tuple(params)).fetchone()[0]
        pickup = conn.execute(
            f"SELECT COUNT(*) FROM orders{base}{joiner}shipping_method = 'pickup'",
            tuple(params),
        ).fetchone()[0]
        cyprus = conn.execute(
            f"SELECT COUNT(*) FROM orders{base}{joiner}"
            "shipping_method = 'delivery' AND delivery_country = 'cyprus'",
            tuple(params),
        ).fetchone()[0]
        greece = conn.execute(
            f"SELECT COUNT(*) FROM orders{base}{joiner}"
            "shipping_method = 'delivery' AND delivery_country = 'greece'",
            tuple(params),
        ).fetchone()[0]
        other = conn.execute(
            f"SELECT COUNT(*) FROM orders{base}{joiner}"
            "shipping_method = 'delivery' AND delivery_country = 'other'",
            tuple(params),
        ).fetchone()[0]
    return {
        "all": int(total),
        "pickup": int(pickup),
        "cyprus": int(cyprus),
        "greece": int(greece),
        "other": int(other),
    }


def order_status_counts(
    *,
    archived: bool = False,
    q: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    shipping: str | None = None,
) -> dict[str, int]:
    """Counts for the admin status filter chips."""
    base, params = _order_filter_sql(
        shipping=shipping,
        q=q,
        archived=archived,
        date_from=date_from,
        date_to=date_to,
    )
    group = f"SELECT status, COUNT(*) AS n FROM orders{base} GROUP BY status"
    total_sql = f"SELECT COUNT(*) FROM orders{base}"
    with get_connection() as conn:
        rows = conn.execute(group, tuple(params)).fetchall()
        total = conn.execute(total_sql, tuple(params)).fetchone()[0]
    counts = {row["status"]: int(row["n"]) for row in rows}
    counts["all"] = int(total)
    return counts


def order_archive_counts(
    *,
    q: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    status: str | None = None,
    shipping: str | None = None,
) -> dict[str, int]:
    """Inbox vs archived counts for the same search/date/shipping filters (not status)."""
    inbox_where, inbox_params = _order_filter_sql(
        status=status,
        shipping=shipping,
        q=q,
        archived=False,
        date_from=date_from,
        date_to=date_to,
    )
    archived_where, archived_params = _order_filter_sql(
        status=status,
        shipping=shipping,
        q=q,
        archived=True,
        date_from=date_from,
        date_to=date_to,
    )
    with get_connection() as conn:
        inbox = conn.execute(
            f"SELECT COUNT(*) FROM orders{inbox_where}", tuple(inbox_params)
        ).fetchone()[0]
        archived = conn.execute(
            f"SELECT COUNT(*) FROM orders{archived_where}", tuple(archived_params)
        ).fetchone()[0]
    return {"inbox": int(inbox), "archived": int(archived)}


def set_order_archived(order_id: int, archived: bool) -> None:
    """Hide a shipped or cancelled order from the inbox (or restore it)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT status FROM orders WHERE id = ?",
            (order_id,),
        ).fetchone()
        if not row:
            raise ValueError("Order not found")
        if archived and row["status"] not in ARCHIVABLE_STATUSES:
            raise ValueError("Only shipped or cancelled orders can be archived")
        conn.execute(
            "UPDATE orders SET archived = ? WHERE id = ?",
            (1 if archived else 0, order_id),
        )


def archive_done_orders(
    *,
    status: str | None = None,
    shipping: str | None = None,
    q: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> int:
    """Archive every shipped or cancelled order currently in the inbox for these filters."""
    where, params = _order_filter_sql(
        status=status,
        shipping=shipping,
        q=q,
        archived=False,
        date_from=date_from,
        date_to=date_to,
    )
    placeholders = ", ".join("?" for _ in ARCHIVABLE_STATUSES)
    extra = f"status IN ({placeholders})"
    params.extend(ARCHIVABLE_STATUSES)
    clause = f"{where} AND {extra}" if where else f" WHERE {extra}"
    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE orders SET archived = 1{clause}",
            tuple(params),
        )
        return int(cursor.rowcount or 0)


def update_order_status(order_id: int, status: str) -> None:
    """Set status and restock when cancelling (or deduct again when reopening)."""
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT status, payment_status FROM orders WHERE id = ?",
            (order_id,),
        ).fetchone()
        if not row:
            raise ValueError("Order not found")

        current = row["status"]
        if current == status:
            return

        items = conn.execute(
            "SELECT product_id, quantity FROM order_items WHERE order_id = ?",
            (order_id,),
        ).fetchall()

        if current != "cancelled" and status == "cancelled":
            for item in items:
                conn.execute(
                    "UPDATE products SET stock = stock + ? WHERE id = ?",
                    (item["quantity"], item["product_id"]),
                )
        elif current == "cancelled" and status != "cancelled":
            if row["payment_status"] == "refunded":
                raise ValueError(
                    "This order was refunded, so it cannot be reopened. "
                    "If they pay again, place a new order."
                )
            for item in items:
                product = conn.execute(
                    "SELECT name, stock FROM products WHERE id = ?",
                    (item["product_id"],),
                ).fetchone()
                if not product or product["stock"] < item["quantity"]:
                    name = product["name"] if product else "item"
                    raise ValueError(f"Insufficient stock to reopen for {name}")
            for item in items:
                conn.execute(
                    "UPDATE products SET stock = stock - ? WHERE id = ?",
                    (item["quantity"], item["product_id"]),
                )

        conn.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
        if status not in ARCHIVABLE_STATUSES:
            conn.execute("UPDATE orders SET archived = 0 WHERE id = ?", (order_id,))


def update_order_notes(order_id: int, notes: str) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE orders SET notes = ? WHERE id = ?", (notes, order_id))


def update_order_tracking(order_id: int, tracking_number: str) -> str:
    cleaned = " ".join((tracking_number or "").split())[:120]
    with get_connection() as conn:
        conn.execute(
            "UPDATE orders SET tracking_number = ? WHERE id = ?",
            (cleaned, order_id),
        )
    return cleaned


def set_payment_status(order_id: int, payment_status: str) -> None:
    if payment_status not in {"unpaid", "paid", "refunded"}:
        raise ValueError("Invalid payment status")
    with get_connection() as conn:
        conn.execute(
            "UPDATE orders SET payment_status = ? WHERE id = ?",
            (payment_status, order_id),
        )


def mark_order_paid_cash(order_id: int) -> None:
    """Record a cash/bank payment. Does not call Stripe."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT payment_status FROM orders WHERE id = ?",
            (order_id,),
        ).fetchone()
        if not row:
            raise ValueError("Order not found")
        if row["payment_status"] != "unpaid":
            raise ValueError("Only unpaid orders can be marked paid in cash")
        conn.execute(
            "UPDATE orders SET payment_status = 'paid', payment_method = 'cash' WHERE id = ?",
            (order_id,),
        )


def _order_from_row(conn, row) -> Order:
    item_rows = conn.execute(
        """
        SELECT oi.quantity, oi.unit_price_cents,
               COALESCE(NULLIF(oi.product_name, ''), p.name, 'Item') AS product_name,
               COALESCE(NULLIF(oi.product_code, ''), p.code, '') AS product_code
        FROM order_items oi
        LEFT JOIN products p ON p.id = oi.product_id
        WHERE oi.order_id = ?
        ORDER BY oi.id
        """,
        (row["id"],),
    ).fetchall()
    items = [
        OrderItem(
            product_name=item["product_name"],
            quantity=item["quantity"],
            unit_price_cents=item["unit_price_cents"],
            product_code=item["product_code"] if "product_code" in item.keys() and item["product_code"] else "",
        )
        for item in item_rows
    ]
    keys = row.keys()
    return Order(
        id=row["id"],
        customer_name=row["customer_name"],
        customer_email=row["customer_email"],
        shipping_address=row["shipping_address"],
        total_cents=row["total_cents"],
        created_at=row["created_at"],
        items=items,
        status=row["status"] if "status" in keys else "new",
        notes=row["notes"] if "notes" in keys else "",
        lookup_token=row["lookup_token"] if "lookup_token" in keys and row["lookup_token"] else "",
        payment_status=row["payment_status"]
        if "payment_status" in keys and row["payment_status"]
        else "unpaid",
        shipping_method=row["shipping_method"] if "shipping_method" in keys and row["shipping_method"] else "",
        delivery_country=row["delivery_country"]
        if "delivery_country" in keys and row["delivery_country"]
        else "",
        tracking_number=row["tracking_number"]
        if "tracking_number" in keys and row["tracking_number"]
        else "",
        customer_notes=row["customer_notes"] if "customer_notes" in keys and row["customer_notes"] else "",
        customer_phone=row["customer_phone"] if "customer_phone" in keys and row["customer_phone"] else "",
        payment_method=row["payment_method"] if "payment_method" in keys and row["payment_method"] else "",
        archived=bool(row["archived"]) if "archived" in keys and row["archived"] else False,
    )


def cart_from_snapshot(raw: str) -> dict[str, int]:
    """Rebuild a session cart dict from Stripe metadata JSON."""
    try:
        pairs = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return {}
    cart: dict[str, int] = {}
    if not isinstance(pairs, list):
        return {}
    for item in pairs:
        if not isinstance(item, list) or len(item) < 2:
            continue
        try:
            pid, qty = int(item[0]), int(item[1])
        except (TypeError, ValueError):
            continue
        if pid > 0 and qty > 0:
            cart[str(pid)] = qty
    return cart


def cart_json_from_lines(lines: list[CartLine]) -> str:
    """Persist product id, qty, and the unit price the customer was charged."""
    return json.dumps(
        [[line.product.id, line.quantity, line.product.price_cents] for line in lines],
        separators=(",", ":"),
    )


def lines_from_cart_json(raw: str) -> list[CartLine]:
    """Rebuild cart lines, preferring stored unit prices when present."""
    try:
        pairs = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(pairs, list):
        return []
    ids: list[int] = []
    parsed: list[tuple[int, int, int | None]] = []
    for item in pairs:
        if not isinstance(item, list) or len(item) < 2:
            continue
        try:
            pid, qty = int(item[0]), int(item[1])
            price = int(item[2]) if len(item) > 2 else None
        except (TypeError, ValueError):
            continue
        if pid > 0 and qty > 0:
            ids.append(pid)
            parsed.append((pid, qty, price))
    products = get_products_by_ids(ids)
    lines: list[CartLine] = []
    for pid, qty, price in parsed:
        product = products.get(pid)
        if not product:
            continue
        if price is not None and price > 0:
            product = replace(product, price_cents=price)
        lines.append(CartLine(product=product, quantity=qty))
    return lines


def save_pending_checkout(
    *,
    session_id: str,
    lines: list[CartLine],
    customer_name: str,
    customer_email: str,
    shipping_address: str,
    shipping_method: str,
    delivery_country: str,
    shipping_cents: int,
    total_cents: int,
    customer_notes: str = "",
    customer_phone: str = "",
) -> None:
    cleaned = (session_id or "").strip()
    if not cleaned:
        raise ValueError("Missing Stripe session id")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO pending_checkouts (
                session_id, cart_json, customer_name, customer_email, shipping_address,
                shipping_method, delivery_country, shipping_cents, total_cents,
                customer_notes, customer_phone
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cleaned,
                cart_json_from_lines(lines),
                customer_name,
                customer_email,
                shipping_address,
                shipping_method,
                delivery_country or "",
                max(0, shipping_cents),
                total_cents,
                (customer_notes or "").strip()[:1000],
                (customer_phone or "").strip()[:40],
            ),
        )


def get_pending_checkout(session_id: str) -> dict[str, Any] | None:
    cleaned = (session_id or "").strip()
    if not cleaned:
        return None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM pending_checkouts WHERE session_id = ?",
            (cleaned,),
        ).fetchone()
    if not row:
        return None
    return {key: row[key] for key in row.keys()}


def place_order(
    *,
    customer_name: str,
    customer_email: str,
    shipping_address: str,
    lines: list[CartLine],
    shipping_cents: int = 0,
    shipping_method: str = "",
    delivery_country: str = "",
    paid: bool = False,
    stripe_session_id: str | None = None,
    customer_notes: str = "",
    customer_phone: str = "",
    payment_method: str = "",
) -> int:
    """Persist an order and decrement stock atomically.

    When stripe_session_id is set, the Stripe mapping is written in the same
    transaction so webhook and /pay/success cannot double-create an order.
    """
    if not lines:
        raise ValueError("Cart is empty")

    total = cart_total_cents(lines) + max(0, shipping_cents)
    payment_status = "paid" if paid else "unpaid"
    method = (shipping_method or "").strip()
    country = (delivery_country or "").strip()
    session_id = (stripe_session_id or "").strip()
    notes = (customer_notes or "").strip()[:1000]
    phone = (customer_phone or "").strip()[:40]
    pay_method = (payment_method or ("card" if paid else "")).strip()[:20]

    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if session_id:
            existing = conn.execute(
                "SELECT order_id FROM stripe_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if existing:
                return int(existing["order_id"])

        for line in lines:
            row = conn.execute(
                "SELECT stock FROM products WHERE id = ?",
                (line.product.id,),
            ).fetchone()
            if not row or row["stock"] < line.quantity:
                raise ValueError(f"Insufficient stock for {line.product.name}")

        token = secrets.token_urlsafe(16)
        cursor = conn.execute(
            """
            INSERT INTO orders (
                customer_name, customer_email, shipping_address, total_cents,
                status, lookup_token, payment_status, shipping_method, delivery_country,
                customer_notes, customer_phone, payment_method
            )
            VALUES (?, ?, ?, ?, 'new', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                customer_name,
                customer_email,
                shipping_address,
                total,
                token,
                payment_status,
                method,
                country,
                notes,
                phone,
                pay_method,
            ),
        )
        order_id = int(cursor.lastrowid)

        for line in lines:
            conn.execute(
                """
                INSERT INTO order_items (order_id, product_id, quantity, unit_price_cents, product_name, product_code)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    line.product.id,
                    line.quantity,
                    line.product.price_cents,
                    line.product.name,
                    line.product.code,
                ),
            )
            conn.execute(
                "UPDATE products SET stock = stock - ? WHERE id = ?",
                (line.quantity, line.product.id),
            )

        if session_id:
            conn.execute(
                "INSERT INTO stripe_sessions (session_id, order_id) VALUES (?, ?)",
                (session_id, order_id),
            )

    return order_id


def order_id_for_stripe_session(session_id: str) -> int | None:
    """Idempotent lookup so a Stripe success refresh does not double-charge stock."""
    cleaned = (session_id or "").strip()
    if not cleaned:
        return None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT order_id FROM stripe_sessions WHERE session_id = ?",
            (cleaned,),
        ).fetchone()
    return int(row["order_id"]) if row else None


def remember_stripe_session(session_id: str, order_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO stripe_sessions (session_id, order_id) VALUES (?, ?)",
            (session_id, order_id),
        )


def stripe_session_id_for_order(order_id: int) -> str | None:
    """Newest Checkout session mapped to this order, if any."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT session_id FROM stripe_sessions WHERE order_id = ? ORDER BY rowid DESC LIMIT 1",
            (order_id,),
        ).fetchone()
    return str(row["session_id"]) if row else None
