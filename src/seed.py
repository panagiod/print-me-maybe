"""Seed catalog from @print.me.maybe posts and LaserCraft 27 custom work."""

from __future__ import annotations

from src.db import get_connection

# 3D listings use captions and euro prices from public @print.me.maybe posts
# when the post named a price. Items Instagram did not price use starting
# prices in line with similar EU listings:
# - Cake toppers: ~€13.50–€16 (custom 3D/silhouette wedding toppers)
# - Bear keychain: ~€5–€11 (3D printed personalized keychains)
# LaserCraft @lasercraft.27 is login-walled; SKUs are custom-order with
# branded placeholders. Prices from similar EU laser work:
# - Oak coaster set of 4: ~€27 (personalized oak sets)
# - Hardwood cutting board: ~€30 (engraved olive/oak boards)
# - Door plaque: ~€15–€16.50 (personalized wooden door signs)
# - Large family name sign: ~€52–€60 (15"–63 cm laser-cut name boards)
CATALOG = [
    {
        "slug": "magical-world-bookshelf",
        "name": "Magical World Bookshelf Decor",
        "description": "3D-printed bookshelf scene inspired by a world of wonder and adventure. Perfect for book lovers. Colour on request — add it in the order notes or DM @print.me.maybe.",
        "price_cents": 1600,
        "image_url": "/static/images/products/magical-world.jpg",
        "category": "3D Prints",
        "stock": 18,
    },
    {
        "slug": "glasses-case",
        "name": "Floral Glasses Case",
        "description": "Lightweight 3D-printed case for prescription glasses or sunglasses, with an embossed floral pattern. Protects from scratches and knocks. Available in several colours — tell us your favourite in the order notes.",
        "price_cents": 400,
        "image_url": "/static/images/products/glasses-case.jpg",
        "category": "3D Prints",
        "stock": 40,
    },
    {
        "slug": "scrunchie-holder",
        "name": "Scrunchie Holder",
        "description": "Holds multiple scrunchies on an arch, with a tray for clips and small accessories. For the bathroom, vanity, or bedroom. Pick a colour in the order notes.",
        "price_cents": 600,
        "image_url": "/static/images/products/scrunchie-holder.jpg",
        "category": "3D Prints",
        "stock": 28,
    },
    {
        "slug": "lip-balm-holder-set",
        "name": "Lip Balm Holder & Name Keychain",
        "description": "Set with a 3D-printed lip balm holder and a custom name keychain. Choose the name and colours in the order notes. Made for bags, keys, or backpacks.",
        "price_cents": 700,
        "image_url": "/static/images/products/lip-balm-holder.jpg",
        "category": "3D Prints",
        "stock": 35,
    },
    {
        "slug": "magic-bookshelf-decor",
        "name": "Wizard Bookshelf Decor",
        "description": "Matte-black bookshelf piece with a flying wizard and castle silhouette. A small gift for fantasy readers. Colour on request.",
        "price_cents": 700,
        "image_url": "/static/images/products/magic-bookshelf.jpg",
        "category": "3D Prints",
        "stock": 22,
    },
    {
        "slug": "minas-tirith",
        "name": "Minas Tirith",
        "description": "Detailed 3D print of the White City of Gondor — a shelf or desk collectible for Lord of the Rings fans.",
        "price_cents": 1000,
        "image_url": "/static/images/products/minas-tirith.jpg",
        "category": "3D Prints",
        "stock": 16,
    },
    {
        "slug": "funny-desk-signs",
        "name": "Funny Desk Signs (5-pack)",
        "description": "Five small 3D-printed quote signs for a desk or shelf. Pick quotes and colours in the order notes — any five pieces for this price.",
        "price_cents": 300,
        "image_url": "/static/images/products/funny-signs.jpg",
        "category": "3D Prints",
        "stock": 50,
    },
    {
        "slug": "articulated-dragon",
        "name": "Articulated Dragon",
        "description": "Poseable 3D-printed dragon for play, décor, or gifting. Colours can be customised — add your preference in the order notes.",
        "price_cents": 1300,
        "image_url": "/static/images/products/dragon.jpg",
        "category": "3D Prints",
        "stock": 20,
    },
    {
        "slug": "dragon-egg",
        "name": "Dragon Egg",
        "description": "Matching 3D-printed dragon egg. Pair it with the articulated dragon, or order the set below and save.",
        "price_cents": 1200,
        "image_url": "/static/images/products/dragon-egg.jpg",
        "category": "3D Prints",
        "stock": 20,
    },
    {
        "slug": "dragon-egg-set",
        "name": "Dragon & Egg Set",
        "description": "Articulated dragon plus matching egg as a set. Colours customisable. A gift for fantasy fans of any age.",
        "price_cents": 2000,
        "image_url": "/static/images/products/dragon-egg.jpg",
        "category": "3D Prints",
        "stock": 14,
    },
    {
        "slug": "custom-cake-topper",
        "name": "Custom Cake Topper",
        "description": "Made-to-order topper for a wedding, baptism, birthday, or baby shower. Add names, dates, and the design in the order notes. Starting price in line with similar custom toppers; we confirm complex designs by DM.",
        "price_cents": 1500,
        "image_url": "/static/images/products/cake-topper.jpg",
        "category": "3D Prints",
        "stock": 30,
    },
    {
        "slug": "bear-keychain",
        "name": "Teddy Bear Keychain",
        "description": "Small 3D-printed bear keychain — a keepsake or class souvenir. Colour on request. Price is for one; class sets via order notes or DM @print.me.maybe.",
        "price_cents": 500,
        "image_url": "/static/images/products/bear-keychain.jpg",
        "category": "3D Prints",
        "stock": 40,
    },
    {
        "slug": "oak-coaster-set",
        "name": "Engraved Oak Coaster Set",
        "description": "Set of four oak coasters, laser-engraved by LaserCraft 27. Add a monogram or short quote in the order notes or DM @lasercraft.27. Photo coming — see Instagram for recent work.",
        "price_cents": 2700,
        "image_url": "/static/images/products/laser-coasters.svg",
        "category": "Laser Engraving",
        "stock": 24,
    },
    {
        "slug": "cutting-board",
        "name": "Personalized Cutting Board",
        "description": "Hardwood board with a name, date, or heading engraved. Food-safe oil finish. Send the text after checkout. Photo coming — see @lasercraft.27.",
        "price_cents": 3000,
        "image_url": "/static/images/products/laser-board.svg",
        "category": "Laser Engraving",
        "stock": 12,
    },
    {
        "slug": "name-plaque",
        "name": "Custom Door Plaque",
        "description": "Laser-cut and engraved name plaque for a studio, nursery, or front door. Wood or acrylic. Photo coming — see @lasercraft.27.",
        "price_cents": 1600,
        "image_url": "/static/images/products/laser-plaque.svg",
        "category": "Laser Engraving",
        "stock": 20,
    },
    {
        "slug": "family-name-sign",
        "name": "Large Family Name Sign",
        "description": "Statement wall sign with family name and established year. Laser-cut lettering on stained wood. Photo coming — see @lasercraft.27.",
        "price_cents": 5500,
        "image_url": "/static/images/products/laser-sign.svg",
        "category": "Laser Engraving",
        "stock": 8,
    },
]


def seed_products() -> None:
    """Insert missing catalog SKUs. Existing rows (including admin edits) are left as-is.

    Stock and products added from studio admin are never overwritten by seed.
    """
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO products (slug, name, description, price_cents, image_url, category, stock)
            VALUES (:slug, :name, :description, :price_cents, :image_url, :category, :stock)
            ON CONFLICT(slug) DO NOTHING
            """,
            CATALOG,
        )
