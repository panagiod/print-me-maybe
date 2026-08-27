"""Seed catalog from @print.me.maybe posts."""

from __future__ import annotations

from src.db import get_connection, sync_product_image_gallery
from src.store import ensure_shop_settings
from src.uploads import promote_static_listing_photos

# 3D listings use captions and euro prices from public @print.me.maybe posts
# when the post named a price. Items Instagram did not price use starting
# prices in line with similar EU listings:
# - Cake toppers: ~€13.50–€16 (custom 3D/silhouette wedding toppers)
# - Bear keychain: ~€5–€11 (3D printed personalized keychains)
# Household décor SKUs (coasters, boards, plaques, signs) use starting
# prices in line with similar EU handmade listings.
#
# CATALOG is empty-database bootstrap only (and tests). Boot never overwrites
# existing rows. image_url paths are keys used to import files into DATA_DIR;
# after first boot the live URLs are /media/products/... in SQLite.
CATALOG = [
    {
        "slug": "magical-world-bookshelf",
        "name": "Magical World Bookshelf Decor",
        "description": "3D-printed bookshelf scene inspired by a world of wonder and adventure. Perfect for book lovers. Colour on request — add it in the order notes or DM @print.me.maybe.",
        "price_cents": 1600,
        "image_url": "/static/images/products/magical-world.jpg",
        "category": "Harry Potter",
        "stock": 18,
    },
    {
        "slug": "glasses-case",
        "name": "Floral Glasses Case",
        "description": "Lightweight 3D-printed case for prescription glasses or sunglasses, with an embossed floral pattern. Protects from scratches and knocks. Available in several colours — tell us your favourite in the order notes.",
        "price_cents": 400,
        "image_url": "/static/images/products/glasses-case.jpg",
        "category": "Household",
        "stock": 40,
    },
    {
        "slug": "scrunchie-holder",
        "name": "Scrunchie Holder",
        "description": "Holds multiple scrunchies on an arch, with a tray for clips and small accessories. For the bathroom, vanity, or bedroom. Pick a colour in the order notes.",
        "price_cents": 600,
        "image_url": "/static/images/products/scrunchie-holder.jpg",
        "category": "Household",
        "stock": 28,
    },
    {
        "slug": "lip-balm-holder-set",
        "name": "Lip Balm Holder & Name Keychain",
        "description": "Set with a 3D-printed lip balm holder and a custom name keychain. Choose the name and colours in the order notes. Made for bags, keys, or backpacks.",
        "price_cents": 700,
        "image_url": "/static/images/products/lip-balm-holder.jpg",
        "category": "Household",
        "stock": 35,
    },
    {
        "slug": "magic-bookshelf-decor",
        "name": "Wizard Bookshelf Decor",
        "description": "Matte-black bookshelf piece with a flying wizard and castle silhouette. A small gift for fantasy readers. Colour on request.",
        "price_cents": 700,
        "image_url": "/static/images/products/magic-bookshelf.jpg",
        "category": "Harry Potter",
        "stock": 22,
    },
    {
        "slug": "minas-tirith",
        "name": "Minas Tirith",
        "description": "Detailed 3D print of the White City of Gondor — a shelf or desk collectible for Lord of the Rings fans.",
        "price_cents": 1000,
        "image_url": "/static/images/products/minas-tirith.jpg",
        "category": "Lord of the Rings",
        "stock": 16,
    },
    {
        "slug": "funny-desk-signs",
        "name": "Funny Desk Signs (5-pack)",
        "description": "Five small 3D-printed quote signs for a desk or shelf. Pick quotes and colours in the order notes — any five pieces for this price.",
        "price_cents": 300,
        "image_url": "/static/images/products/funny-signs.jpg",
        "category": "Household",
        "stock": 50,
    },
    {
        "slug": "articulated-dragon",
        "name": "Articulated Dragon",
        "description": "Poseable 3D-printed dragon for play, décor, or gifting. Colours can be customised — add your preference in the order notes.",
        "price_cents": 1300,
        "image_url": "/static/images/products/dragon.jpg",
        "category": "Lord of the Rings",
        "stock": 20,
    },
    {
        "slug": "dragon-egg",
        "name": "Dragon Egg",
        "description": "Matching 3D-printed dragon egg. Pair it with the articulated dragon, or order the set below and save.",
        "price_cents": 1200,
        "image_url": "/static/images/products/dragon-egg.jpg",
        "category": "Lord of the Rings",
        "stock": 20,
    },
    {
        "slug": "dragon-egg-set",
        "name": "Dragon & Egg Set",
        "description": "Articulated dragon plus matching egg as a set. Colours customisable. A gift for fantasy fans of any age.",
        "price_cents": 2000,
        "image_url": "/static/images/products/dragon-egg.jpg",
        "category": "Lord of the Rings",
        "stock": 14,
    },
    {
        "slug": "custom-cake-topper",
        "name": "Custom Cake Topper",
        "description": "Made-to-order topper for a wedding, baptism, birthday, or baby shower. Add names, dates, and the design in the order notes. Starting price in line with similar custom toppers; we confirm complex designs by DM.",
        "price_cents": 1500,
        "image_url": "/static/images/products/cake-topper.jpg",
        "category": "Household",
        "stock": 30,
    },
    {
        "slug": "bear-keychain",
        "name": "Teddy Bear Keychain",
        "description": "Small 3D-printed bear keychain — a keepsake or class souvenir. Colour on request. Price is for one; class sets via order notes or DM @print.me.maybe.",
        "price_cents": 500,
        "image_url": "/static/images/products/bear-keychain.jpg",
        "category": "Household",
        "stock": 40,
    },
    {
        "slug": "oak-coaster-set",
        "name": "Oak Coaster Set",
        "description": "Set of four oak coasters. Add a monogram or short quote in the order notes or DM @print.me.maybe.",
        "price_cents": 2700,
        "image_url": "/static/images/products/laser-coasters.svg",
        "category": "Household",
        "stock": 24,
    },
    {
        "slug": "cutting-board",
        "name": "Personalized Cutting Board",
        "description": "Hardwood board with a name, date, or heading. Food-safe oil finish. Send the text after checkout or DM @print.me.maybe.",
        "price_cents": 3000,
        "image_url": "/static/images/products/laser-board.svg",
        "category": "Household",
        "stock": 12,
    },
    {
        "slug": "name-plaque",
        "name": "Custom Door Plaque",
        "description": "Name plaque for a studio, nursery, or front door. Wood or acrylic. Add the wording in the order notes or DM @print.me.maybe.",
        "price_cents": 1600,
        "image_url": "/static/images/products/laser-plaque.svg",
        "category": "Household",
        "stock": 20,
    },
    {
        "slug": "family-name-sign",
        "name": "Large Family Name Sign",
        "description": "Statement wall sign with family name and established year. Lettering on stained wood. Add the wording in the order notes or DM @print.me.maybe.",
        "price_cents": 5500,
        "image_url": "/static/images/products/laser-sign.svg",
        "category": "Household",
        "stock": 8,
    },
]
SEED_CODES = {
    "magical-world-bookshelf": "3D-BOOKSHELF",
    "glasses-case": "3D-GLASSES",
    "scrunchie-holder": "3D-SCRUNCHIE",
    "lip-balm-holder-set": "3D-LIPBALM",
    "magic-bookshelf-decor": "3D-WIZARD",
    "minas-tirith": "3D-MINAS",
    "funny-desk-signs": "3D-SIGNS",
    "articulated-dragon": "3D-DRAGON",
    "dragon-egg": "3D-EGG",
    "dragon-egg-set": "3D-SET",
    "custom-cake-topper": "3D-TOPPER",
    "bear-keychain": "3D-BEAR",
    "oak-coaster-set": "LC-COASTERS",
    "cutting-board": "LC-BOARD",
    "name-plaque": "LC-PLAQUE",
    "family-name-sign": "LC-SIGN",
}
for _item in CATALOG:
    _item["code"] = SEED_CODES[_item["slug"]]


def remap_legacy_categories() -> None:
    """Rename leftover 3D/laser genre labels. Studio edits on known slugs are left as-is."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE products SET category = 'Household' WHERE category IN ('3D Prints', 'Laser Engraving')"
        )


def seed_products() -> None:
    """Fill an empty catalog from CATALOG. Never re-inserts listings you removed.

    Existing rows (including admin edits) are left as-is. Empty product codes on
    known slugs are filled once. Listing photos still pointed at
    /static/images/products/ are copied into DATA_DIR and rewritten to /media.
    """
    with get_connection() as conn:
        remaining = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        if remaining == 0:
            conn.executemany(
                """
                INSERT INTO products (slug, name, description, price_cents, image_url, category, stock, code)
                VALUES (:slug, :name, :description, :price_cents, :image_url, :category, :stock, :code)
                """,
                CATALOG,
            )
        conn.executemany(
            """
            UPDATE products SET code = :code
            WHERE slug = :slug AND COALESCE(code, '') = ''
            """,
            CATALOG,
        )
    remap_legacy_categories()
    sync_product_image_gallery()
    promote_static_listing_photos()
    ensure_shop_settings()
