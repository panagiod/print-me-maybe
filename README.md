# Print Me Maybe (Hetzner)

**Live shop:** [print-me-maybe.com](https://print-me-maybe.com) — [Print Me Maybe](https://www.instagram.com/print.me.maybe/) on a Hetzner VPS with persistent storage, Stripe Checkout, and Resend emails.

Studio login: [print-me-maybe.com/admin/login](https://print-me-maybe.com/admin/login) (not linked in the public nav). Password is in `/etc/eshop.env` as `ADMIN_PASSWORD`.

## Purpose

| | |
|---|---|
| **This repo** | [panagiod/print-me-maybe](https://github.com/panagiod/print-me-maybe) — live Hetzner shop, persistent disk, real card payments |
| **Not this repo** | [panagiod/eshop](https://github.com/panagiod/eshop) (`main`) — free Render demo at [print-me-maybe.onrender.com](https://print-me-maybe.onrender.com) |

The two repos share the same Python app but serve different hosts. **Do not merge this tree into `eshop` `main`** — the Render shop stays as-is.

**Why Hetzner?** Orders and product photos live on disk (`/var/lib/eshop`) instead of ephemeral `/tmp` on Render Free. Fixed cost is about **€8/month** (CX23 + VAT) + **~$11/year** for a domain. Stripe charges **1.5% + €0.25** on EEA cards with no monthly fee. That original card fee is **kept by Stripe** if you later cancel and refund (the customer still gets the full amount back).

## Status

The shop is **in production**. Push to `main` deploys automatically.

| Step | Issue | State |
|------|-------|--------|
| Buy domain | [#8](https://github.com/panagiod/print-me-maybe/issues/8) | Done — `print-me-maybe.com` |
| Provision VPS | [#7](https://github.com/panagiod/print-me-maybe/issues/7) | Done — live server |
| Point DNS | [#3](https://github.com/panagiod/print-me-maybe/issues/3) | Done |
| Deploy shop | [#5](https://github.com/panagiod/print-me-maybe/issues/5) | Done — CI/CD on `main` |
| Stripe Checkout | [#6](https://github.com/panagiod/print-me-maybe/issues/6) | Done — webhook + secret on the VPS |
| Resend emails | [#2](https://github.com/panagiod/print-me-maybe/issues/2) | Done |
| Paid order survives reboot | [#4](https://github.com/panagiod/print-me-maybe/issues/4) | Still worth doing once |

The [Go live](#go-live-cheapest-stack) sections below are a rebuild record, not a to-do list.

## Contents

- [Purpose](#purpose)
- [Status](#status)
- [What this project is](#what-this-project-is)
- [Go live (cheapest stack)](#go-live-cheapest-stack)
- [Buy a Hetzner CX23 server](#buy-a-hetzner-cx23-server)
- [Point DNS at the Hetzner server](#point-dns-at-the-hetzner-server)
- [Features](#features)
- [Stack](#stack)
- [Repository layout](#repository-layout)
- [Local development](#local-development)
- [Tests and CI](#tests-and-ci)
- [CI/CD deployment](#cicd-deployment)
- [Configuration](#configuration)
- [Shop behaviour](#shop-behaviour)
- [Shipping](#shipping)
- [Studio admin](#studio-admin)
- [How customers follow an order](#how-customers-follow-an-order)
- [Payments and refunds](#payments-and-refunds)
- [Order emails](#order-emails)
- [Security](#security)
- [Backups](#backups)
- [License](#license)

## What this project is

| This project **does** | This project **does not** |
|-----------------------|---------------------------|
| Keep orders and photos on the Hetzner disk (`/var/lib/eshop`) | Wipe data on sleep (Render Free does that) |
| Take **card payment** via Stripe Checkout when `STRIPE_SECRET_KEY` is set | Charge a monthly Stripe or Shopify fee |
| Email studio and customer via Resend after you verify **your** domain | Send from `onboarding@resend.dev` or `outlook.com` |

Custom names/files can be typed in **order notes** at checkout, or still go over **Instagram DM**.

## Go live (cheapest stack)

These steps are **already done** for `print-me-maybe.com`. Kept so you can rebuild or compare against the original issues.

Track leftover checks in [Issues](https://github.com/panagiod/print-me-maybe/issues). Summary:

1. **Domain** — **done:** `print-me-maybe.com` ([#8](https://github.com/panagiod/print-me-maybe/issues/8))
2. **Server** — **done:** Hetzner Cloud **CX23** ([#7](https://github.com/panagiod/print-me-maybe/issues/7)) — see [Buy a Hetzner CX23 server](#buy-a-hetzner-cx23-server) below.
3. **DNS** — **done:** ([#3](https://github.com/panagiod/print-me-maybe/issues/3)) — see [Point DNS at the Hetzner server](#point-dns-at-the-hetzner-server) below.
4. **Install** — **done:** ([#5](https://github.com/panagiod/print-me-maybe/issues/5)). SSH as root was the one-time bootstrap:

   ```bash
   git clone https://github.com/panagiod/print-me-maybe.git /opt/eshop
   bash /opt/eshop/deploy/install.sh
   ```

   Then set up [CI/CD](#cicd-deployment) so every push to `main` deploys automatically.

   Manual update anytime: `bash /opt/eshop/deploy/deploy.sh`

   `install.sh` generates `SESSION_SECRET` and `ADMIN_PASSWORD` and prints the admin password once. Caddy gets HTTPS automatically after DNS points at the server.
5. **Stripe** — **done:** ([#6](https://github.com/panagiod/print-me-maybe/issues/6)) [dashboard.stripe.com](https://dashboard.stripe.com) → activate payments, EUR, copy the **secret** key into `STRIPE_SECRET_KEY`. Add a webhook endpoint `https://print-me-maybe.com/webhooks/stripe` for `checkout.session.completed` and put the signing secret in `STRIPE_WEBHOOK_SECRET`. Checkout redirects to Stripe; the order is created from the webhook (or `/pay/success`) only after `payment_status=paid`.
6. **Resend** — **done:** ([#2](https://github.com/panagiod/print-me-maybe/issues/2)) [resend.com/domains](https://resend.com/domains) → add `print-me-maybe.com` (not `onrender.com`) → paste DNS records → wait for **Verified** → set `RESEND_FROM=Print Me Maybe <orders@print-me-maybe.com>`.
7. **Smoke test** — still open: [#4](https://github.com/panagiod/print-me-maybe/issues/4) Check `https://print-me-maybe.com/health` — `"payments": true`, `"persistent": true`. Place a **test** card order (`ACCT-000015`), reboot the VPS, confirm the order is still in studio.

Until `STRIPE_SECRET_KEY` is set, checkout stays a no-card demo (same as the Render shop). Production has the key set (`/health` shows `"payments": true`).

## Buy a Hetzner CX23 server

Tracked as [#7](https://github.com/panagiod/print-me-maybe/issues/7). You want **Hetzner Cloud** (VPS), not “Robot” dedicated servers.

| Item | Choice |
|------|--------|
| Sign up | https://www.hetzner.com/cloud → **Console** at https://console.hetzner.cloud |
| Plan | **CX23** (Shared vCPU) — ~€5.49/month + VAT |
| OS | **Ubuntu 24.04** |
| Location | **Falkenstein** or **Helsinki** |
| Access | **SSH key** (recommended) or root password emailed by Hetzner |

### 1. Account and project

1. Create a Hetzner account and add a **payment method**.
2. In the console, **New project** → e.g. `print-me-maybe`.

### 2. SSH key (before creating the server)

On your laptop:

```bash
ssh-keygen -t ed25519 -C "print-me-maybe" -f ~/.ssh/print-me-maybe
cat ~/.ssh/print-me-maybe.pub
```

In the console: **Security** → **SSH keys** → **Add SSH key** → paste the `.pub` line.

### 3. Create the server

**Servers** → **Add Server**:

1. **Location** — Falkenstein (`fsn1`) or Helsinki (`hel1`)
2. **Image** — Ubuntu **24.04**
3. **Type** — **Shared vCPU** tab → **CX23**
4. **Networking** — keep **Public IPv4** on (needed for `print-me-maybe.com`)
5. **SSH keys** — select your key
6. **Name** — e.g. `print-me-maybe`
7. **Create & Buy now**

### 4. Connect and save the IP

Copy the server **IPv4** from the overview page, then:

```bash
ssh -i ~/.ssh/print-me-maybe root@YOUR_SERVER_IPV4
```

Use that IPv4 in [#3 DNS](https://github.com/panagiod/print-me-maybe/issues/3), then continue with [#5 deploy](https://github.com/panagiod/print-me-maybe/issues/5).

## Point DNS at the Hetzner server

Tracked as [#3](https://github.com/panagiod/print-me-maybe/issues/3). This tells the internet that **print-me-maybe.com** should reach your Hetzner box.

**You need first:** the server **IPv4** from [#7](https://github.com/panagiod/print-me-maybe/issues/7) (e.g. `95.xxx.xxx.xxx`).

### What to add

Two **A records** — both point at the same Hetzner IPv4:

| Type | Name / Host | Value | TTL |
|------|-------------|-------|-----|
| A | `@` (or `print-me-maybe.com`) | your Hetzner IPv4 | Auto / 300 |
| A | `www` | same IPv4 | Auto / 300 |

- **A** = IPv4 address (not AAAA — that is IPv6; optional later).
- **`@`** = the bare domain `print-me-maybe.com`.
- **`www`** = `www.print-me-maybe.com`.

Leave **IPv6 on** at Hetzner if you want; these A records are still required for most visitors.

### Cloudflare (if you bought the domain there)

1. Log in at https://dash.cloudflare.com
2. Click **print-me-maybe.com**
3. Left sidebar → **DNS** → **Records**
4. **Add record** → Type **A**, Name **@**, IPv4 address = Hetzner IP → **Proxy status: DNS only** (grey cloud, not orange) → Save
5. **Add record** → Type **A**, Name **www**, same IP → **DNS only** → Save

**Why grey cloud (DNS only)?** Caddy on the VPS talks to Let's Encrypt directly. Orange-cloud proxy works too but needs extra Cloudflare SSL settings — grey cloud is the simple path for this setup.

### Other DNS providers

Same two A records in wherever you manage DNS (registrar panel, Cloudflare, etc.). Names may differ slightly:

- **Name `@`** might appear as `print-me-maybe.com`, blank, or “root”.
- **Name `www`** is usually just `www`.

### Check it worked

On your laptop (may take a few minutes to propagate):

```bash
dig print-me-maybe.com +short
dig www.print-me-maybe.com +short
```

Both commands should print your **Hetzner IPv4**. If they show nothing or a wrong IP, wait 5–15 minutes and try again.

### What happens next

Once DNS resolves, continue [#5 Deploy the shop](https://github.com/panagiod/print-me-maybe/issues/5). After `install.sh` and `systemctl reload caddy`, Caddy will fetch HTTPS certificates automatically for `print-me-maybe.com` and `www.print-me-maybe.com`.

Resend TXT/MX records for email ([#2](https://github.com/panagiod/print-me-maybe/issues/2)) go in the **same** DNS panel later — they do not replace these A records.

## Features

- Catalog with category filter (3D Prints / Laser Engraving); product pages can show a photo gallery
- Session cart; quantity cannot exceed stock
- Shipping chosen at checkout (see [Shipping](#shipping)): pick up free, Cyprus delivery €3.50, Greece delivery €10
- Checkout: name, email, phone (required for delivery), street / city / postcode, optional order notes, pick-up or delivery (Cyprus or Greece), **card (Stripe)** or **cash at pick up**
- Customer order page at `/order/{unguessable-token}` — status, payment, tracking number, notes (times in Europe/Nicosia)
- Studio at `/admin` (not linked in public nav): orders (search, shipping filters), tracking, customer/studio notes, copy customer link, resend mail, cash/bank paid, packing slip (print + PDF), cancel (Stripe refund + restock + customer email), catalog with photos, hide/show, add/edit/remove product + gallery
- Emails via [Resend](https://resend.com): new order (studio + customer), ready to collect/pack, shipped (customer; delivery waits for tracking), cancelled (studio + customer), attack alerts
- JSON catalog at `GET /api/products`
- Liveness at `GET /health` (`mail`, `payments`, `persistent`)

## Stack

- **Python 3.12**, [FastAPI](https://fastapi.tiangolo.com/), Uvicorn
- **Jinja2** HTML templates + `static/css`
- **SQLite** under `DATA_DIR` (local default `/tmp/eshop-data`; production `/var/lib/eshop`), schema via **Alembic**
- **Pillow** resizes studio photo uploads (display + catalog thumb)
- **HTMX** (vendored) for in-place Stock qty / hide / show
- **WeasyPrint** for packing-slip PDFs (needs cairo/pango on the VPS)
- Signed **session cookies** for cart and studio login
- GitHub Actions CI: pytest + smoke `curl` of `/health` and home

## Repository layout

```
src/                 FastAPI app
  main.py            Storefront routes (home, product, cart, checkout, health)
  admin.py           Studio login, orders, tracking, stock, add/edit/remove product, gallery, packing slip, test email
  store.py           Products, cart lines, place_order, pending Stripe checkouts
  db.py              SQLite helpers and DATA_DIR
  migrate.py         Alembic upgrade entry point
  models.py          Product/Order types, EUR formatting, shipping rules
  seed.py            Catalog copied from Instagram listings
  uploads.py         Admin product photos (resize, thumbs, unique filenames)
  pdf.py             Packing-slip PDF via WeasyPrint
  payments.py        Stripe Checkout, webhooks, refunds
  fulfill.py         Paid Stripe session → order (idempotent)
  notify.py          Resend/SMTP mail, attack alerts, customer confirmation / shipped / cancelled
  ratelimit.py       Per-IP limits
  security.py        Secrets, HTTPS cookies, CSP/HSTS
templates/           HTML (base, shop, cart, checkout, admin)
static/              CSS, vendored HTMX, and seed product images
alembic/             SQLite migrations
tests/               pytest
deploy/              Hetzner systemd unit, Caddyfile, install.sh, deploy.sh, env.example, backup.sh
.github/workflows/ci.yml
.github/workflows/deploy.yml
```

## Local development

Requires Python 3.12+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn src.main:app --reload --port 8080
```

Open [http://localhost:8080](http://localhost:8080). Studio: [http://localhost:8080/admin/login](http://localhost:8080/admin/login) — password `printmemaybe` unless you set `ADMIN_PASSWORD`.

SQLite and uploaded photos go to `DATA_DIR` (default `/tmp/eshop-data`).

## Tests and CI

```bash
python3 -m pytest tests/ -v
```

GitHub Actions (`.github/workflows/ci.yml`) runs on every pull request and on push to `main`: install cairo/pango (WeasyPrint), pip deps, pytest, then boot Uvicorn and `curl` `/health` and `/`.

Shop tests cover pick-up (free), Cyprus delivery (€3.50, street/city/postcode and phone required), Greece delivery (€10), checkout notes, **cash at pick up** (skips Stripe; delivery cannot be cash), studio product delete (including the block when a product has already been ordered), admin cancel (restock; Stripe refund when paid by card, not for cash), cash/bank mark-paid, ready and shipped emails, shipping a tracking number to the customer order page, photo thumbs, Alembic upgrades from a legacy SQLite file, HTMX stock fragments, and packing-slip PDFs.

## CI/CD deployment

After the [one-time bootstrap](#go-live-cheapest-stack) (`install.sh` on the server), every **push to `main`** that passes CI automatically deploys to Hetzner via `.github/workflows/deploy.yml`.

**Flow:** push to `main` → CI tests pass → GitHub SSHs into the server → `deploy/deploy.sh` pulls latest code → restarts `eshop` and reloads Caddy.

### One-time server bootstrap

On the Hetzner server as `root` (only needed once):

```bash
git clone https://github.com/panagiod/print-me-maybe.git /opt/eshop
bash /opt/eshop/deploy/install.sh
```

Save the printed `ADMIN_PASSWORD`. Edit `/etc/eshop.env` for Stripe/Resend when ready.

### GitHub deploy key (repo secrets)

Create a dedicated SSH key for GitHub Actions (on your laptop — **not** on the server):

```bash
ssh-keygen -t ed25519 -C "github-deploy-print-me-maybe" -f ~/.ssh/github-deploy-print-me-maybe -N ""
cat ~/.ssh/github-deploy-print-me-maybe.pub
```

On the **server**, add the public key so GitHub can SSH in:

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo 'PASTE_THE_.pub_LINE_HERE' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

In GitHub: **Settings → Secrets and variables → Actions → New repository secret**

| Secret | Value |
|--------|--------|
| `SSH_HOST` | Hetzner IPv4 or `print-me-maybe.com` |
| `SSH_USER` | `root` |
| `SSH_PRIVATE_KEY` | entire contents of `~/.ssh/github-deploy-print-me-maybe` (private key) |

Optional: `SSH_PORT` if SSH is not on port 22.

### Manual deploy

- **From the server:** `bash /opt/eshop/deploy/deploy.sh`
- **From GitHub:** Actions → **Deploy** → **Run workflow**

`/etc/eshop.env` (secrets, Stripe, Resend) is **not** overwritten by deploy — only application code and service configs update.

## Configuration

Set these in `/etc/eshop.env` on the server (`deploy/env.example`). Never commit secrets or paste API keys into git/chat. After changes: `systemctl restart eshop`.

| Variable | Default | Purpose |
|----------|---------|---------|
| `ENV` | unset locally; `production` on the VPS | Requires `SESSION_SECRET` and `ADMIN_PASSWORD` |
| `SESSION_SECRET` | generated by `install.sh` | Signs session cookies; **required** in production |
| `ADMIN_PASSWORD` | `printmemaybe` locally; generated by `install.sh` | Studio login |
| `SESSION_HTTPS_ONLY` | on when `ENV=production` | Secure cookie flag |
| `SHOP_NAME` | `Print Me Maybe` | Branding |
| `SHOP_URL` | your `https://` domain | Links in emails |
| `SHOP_TIMEZONE` | `Europe/Nicosia` | Display timezone for order timestamps |
| `DATA_DIR` | `/tmp/eshop-data` locally; `/var/lib/eshop` in production | SQLite + uploaded photos |
| `NOTIFY_EMAIL` | `dimitrioupanagiotis@outlook.com` | Inbox for order and attack alerts |
| `RESEND_API_KEY` | empty (mail skipped) | Resend API key (`re_…`) |
| `RESEND_FROM` | `Print Me Maybe <beth.t@example.com>` | Must be an address on a **verified** Resend domain |
| `STRIPE_SECRET_KEY` | empty (demo checkout, no card) | Stripe secret key (`sk_test_…` or `sk_live_…`) |
| `STRIPE_WEBHOOK_SECRET` | empty | Stripe webhook signing secret (`whsec_…`) for `POST /webhooks/stripe` |
| `ATTACK_ALERT_COOLDOWN` | `3600` | Seconds between similar security emails |
| `NOTIFY_SYNC` | unset | Set to `1` in tests so checkout waits for mail |
| `RATE_LIMIT_DISABLED` | unset | Set to `1` to turn limits off (tests) |

`GET /health` includes `"mail"` and `"payments"` (booleans, no secrets) and `"persistent"` (true when `DATA_DIR` is not under `/tmp`).

Two dashboards that are easy to mix up:

| Site | URL | Role |
|------|-----|------|
| **Hetzner** | https://console.hetzner.cloud | Runs the website (this server) |
| **Stripe** | https://dashboard.stripe.com | Card payments |
| **Resend** | https://resend.com | Sends email |
| **Render** | https://dashboard.render.com | The *old* Free shop only (`panagiod/eshop`) |

## Shop behaviour

**Catalog.** Seed products live in `src/seed.py` (names, **product codes**, euro prices, photos from public Instagram where a price was named). On boot, missing slugs are inserted. **Existing rows are left as-is** — admin price, name, photo, category, stock, and code survive deploy/restart. Products added in studio are never overwritten. Each product can have **several photos**; `image_url` is the cover (first gallery image) used on cards and in the cart. Codes (`3D-GLASSES`, `LC-BOARD`, or the next `3D-001` / `LC-001`) show on Stock, packing slips, and studio order emails, and are snapshotted onto each order line.

**Cart.** Stored in the signed session cookie (7 days). Add/update quantity is capped at remaining stock. Zero stock hides a product from the shop and the product page shows **Sold out** (no Add to cart). **Hidden** products (studio toggle) are omitted from the shop and product URLs 404. The cart shows the product subtotal only; shipping is not applied until checkout.

**Checkout.** GET `/checkout` collects name, email, optional phone, optional order notes (colour, name, files), and a delivery choice (pick up vs ship) as two cards. Payment is two submit buttons: **Pay with card** and **Pay with cash at pick up** (cash is hidden for delivery). Delivery requires a destination card (**Cyprus** or **Greece**), street, city, postcode, and a phone number. POST `/checkout` then:

1. Recalculates shipping from the chosen method and destination (see [Shipping](#shipping)).
2. **Cash at pick up:** places an Unpaid order immediately (`payment_method=cash`), skips Stripe, emails the customer to bring cash, and empties the cart.
3. **Card** (when Stripe is configured): the browser goes to Stripe Checkout. Shipping is a separate Stripe line item when it is more than €0. The cart, shipping method, destination, unit prices, totals, notes, and phone are stored in SQLite (`pending_checkouts`) keyed by the Stripe session id (Stripe metadata is a backup). The order is created when Stripe sends `checkout.session.completed` to `POST /webhooks/stripe`, or when the customer lands on `GET /pay/success`. Both paths are idempotent and **empty the session cart**.
4. If creating the order fails after a **card** payment (for example stock ran out), the shop refunds the PaymentIntent and emails the studio.
5. Without Stripe, card checkout is the no-card demo and still stores the same total (subtotal + shipping). Cash at pick up still sets `payment_method=cash`.

Pick-up orders store method `pickup` and address `Pick up at studio`. Delivery orders store `shipping_method`, `delivery_country` (`cyprus` or `greece`), a composed `shipping_address` (street, city, postcode, country name), and `customer_phone`. Older orders may still have `delivery_country=other` (international). Customer notes are stored separately from studio notes.

**Customer order URL.** `/order/{lookup_token}` — random token, not the numeric id. Guessing `/order/12` returns 404. The thank-you page and the confirmation email both include this link. Times on that page (and in studio) are shown in **Europe/Nicosia**.

The page shows:

- Status: New, In progress, Ready to ship, Shipped, or Cancelled
- Payment: Unpaid, Paid, or Refunded
- Shipping method and address
- Phone (when given)
- Customer notes (when given)
- Tracking number, once you save one in studio (see [How customers follow an order](#how-customers-follow-an-order))

Confirmation, order pages, and emails also show the shipping method label plus Free / €3.50 / €10. Line item names are snapshotted on the order, so renaming a product later does not rewrite history.

## Shipping

Rates are decided at checkout, not from cart size. There is no free-shipping threshold.

| Method | Destination | Charge | Constant in `src/models.py` |
|--------|-------------|--------|-----------------------------|
| Pick up at studio | — | Free | `shipping_cents("pickup")` → `0` |
| Delivery | Cyprus | €3.50 | `CYPRUS_SHIPPING_CENTS = 350` |
| Delivery | Greece | €10.00 | `INTERNATIONAL_SHIPPING_CENTS = 1000` (same rate as leftover `other` orders) |

- Cart copy: “Pick up is free. Cyprus delivery is €3.50. Delivery in Greece is €10.”
- Home hero: “Free pick up; €3.50 delivery in Cyprus; €10 delivery in Greece.”
- Checkout totals update in the browser when the customer switches pick-up / delivery or Cyprus / Greece. The server recomputes the same numbers on POST (and again from Stripe metadata after payment). Shipping is taken from the **country** card, not from a free-text country name.
- Delivery address is **street**, **city**, and **postcode** (plus the Cyprus/Greece card). Those fields are joined into `orders.shipping_address` so packing slips, emails, and Stripe metadata stay one text block.
- **Pay with cash at pick up** is offered on checkout when pick up is selected. That places an **Unpaid** order with `payment_method=cash` and does **not** open Stripe. Delivery is card only. Studio **Mark as paid (cash/bank)** when they collect.
- The `orders` table stores `shipping_method`, `delivery_country`, `shipping_address`, `tracking_number`, `customer_notes`, `customer_phone`, `payment_method`, `archived` (shipped/cancelled orders can leave the inbox), and a combined `total_cents` (subtotal + shipping). Shipping itself is also derived as `total_cents − item subtotal`.

## Studio admin

Public nav does not advertise `/admin`. Login: `/admin/login` on your domain (production: [print-me-maybe.com/admin/login](https://print-me-maybe.com/admin/login)).

| Page | What it does |
|------|----------------|
| `/admin/orders` | Filter by status, shipping (pickup / Cyprus / Greece / leftover international), and **date range (Cyprus time)**; **newest / oldest**; search by number, name, email, tracking, or **product code**; **Inbox vs Archived**; bulk-archive shipped/cancelled in the current view; Paid / Unpaid / Refunded; **Send test email** |
| `/admin/orders/{id}` | Status, **tracking number**, customer notes vs studio notes, phone (`tel:`), copy customer link, resend confirmation (and shipped email), **Mark as paid (cash/bank)**, **Archive** shipped/cancelled (or **Restore to inbox**), print packing slip, **download PDF**, Stripe session id, cancel (Stripe refund if card-paid, restock, email customer) / reopen (blocked if refunded) |
| `/admin/orders/{id}/print` | Packing slip (print hides the admin chrome) |
| `/admin/orders/{id}/print.pdf` | Same slip as a downloadable PDF |
| `/admin/stock` | Catalog with **photos** and **product codes**; search by name or code; category and listed/hidden chips; qty / hide / show save in place; **Add product**; **Remove** (confirm) |
| `/admin/products/new` | Add a product with optional **product code** (blank assigns the next 3D/LC code), photo preview (several photos allowed; first is the cover) |
| `/admin/products/{id}/edit` | Name/price/copy/stock/**code**; **current photos**; add/remove/set cover; view in shop |

### Daily order flow

1. Open **Orders**. The default **Inbox** hides archived shipped and cancelled orders. New **card** checkouts show **Paid**. Cash-at-pick-up orders show **Unpaid · cash**. Use search, date From/To (Cyprus time), Newest/Oldest, or Pickup / Cyprus / Greece chips on packing day.
2. Open the order. Set status **In progress** then **Ready to ship** as you work. Ready emails the customer once (pickup: collect at studio; delivery: packed for courier). Studio notes are yours; customer notes came from checkout.
3. When it leaves: set status **Shipped**. For **delivery**, paste the courier number in **Tracking number** and Save — the customer is emailed only when a tracking number exists. Pickup customers get a collect-at-studio email (no tracking nag).
4. You can add the tracking number later; saving a new number on an already-shipped delivery emails the customer again.
5. When an order is **Shipped** or **Cancelled**, **Archive** it (or **Archive shipped and cancelled in this view** on the list) so it leaves the inbox. Open **Archived** to find it later; **Restore to inbox** brings it back. Reopening a shipped/cancelled order also returns it to the inbox.
6. If they lost the confirmation mail: **Copy customer link** or **Resend confirmation**.

After Save, the order page shows whether the customer email was sent, skipped (no Resend key), failed, or still needs a tracking number.

Order statuses: New → In progress → Ready to ship → Shipped, plus Cancelled.

### Cancel

**Cancel a paid order** from that order page. The browser asks you to confirm first (and shows the refund amount for card orders). The shop refunds the Stripe Checkout payment first; if Stripe rejects the refund, the order stays open and stock is not put back. After a successful refund the payment pill shows **Refunded**, items return to stock, and the customer (and studio inbox) get a cancellation email. **Refunded orders cannot be reopened** — if they pay again, place a new order.

Unpaid demo orders skip Stripe and still email the customer. Orders marked **Paid (cash/bank)** restock and email on cancel and **do not** call Stripe. Reopening a cancelled unpaid order deducts stock again and does **not** charge a card.

Stripe keeps the original card processing fee on a refund (see [Payments and refunds](#payments-and-refunds)).

### Cash / bank

Pickup customers can choose **Pay with cash at pick up** at checkout. The order is placed immediately (Unpaid, no Stripe). Confirmation mail tells them to bring cash; Ready / collect emails repeat the amount. On collection, **Mark as paid (cash/bank)** on the unpaid order. Cancelling that order will not attempt a card refund.

Delivery cannot be cash — those orders still go to Stripe Checkout.

### Catalog

Studio **Stock** is a photo grid. Search by name, filter by line (3D / laser) or Listed / Hidden.

**Add a product.** `/admin/products/new` — name, description, price, category, **product code** (optional), stock, and one or more photos (preview before save). After save you return to Stock with an “added” banner. Leave the code blank to get the next `3D-001` or `LC-001`.

**Photos.** Edit shows the current gallery. The **cover** is the shop card and cart thumb; extra photos appear as a gallery on `/product/{slug}`. You can add files, **Make cover**, or **Remove** a photo. Uploads (JPG/PNG/WebP/GIF, 5 MB each) are stored uniquely under `DATA_DIR/product-images`. **Pillow** auto-rotates, strips EXIF, writes a display image (max 1600px) and a **thumb** (max 400px). Catalog cards, cart, and gallery thumbs use the thumb; the product page main image uses the display file.

**Hide from shop.** **Hide** keeps the SKU and orders; it disappears from `/`, `/api/products`, and product URLs. **Show in shop** lists it again. Qty, Hide, and Show on Stock update that card **in place** (HTMX); without JavaScript they still POST and reload the page. Sold out (qty 0) is separate: the product page still exists but cannot be added to the cart.

**Remove a product.** Each card has **Remove** (`POST /admin/products/{id}/delete`) and asks for confirm. Deletion is a hard delete. It is **blocked** if that product appears on any past order. In that case the studio sees that it cannot be deleted, plus **Hide from shop**. Setting stock to 0 still marks sold out without deleting history. Zero-stock and hidden cards are highlighted; sold-out and hidden sort after listed in-stock items.

Uploaded photos are served from `/media/products/...` and stored under `DATA_DIR/product-images`.

**Packing slip PDF.** From an order, **Print packing slip** still opens the HTML view. **Download PDF** saves `order-{id}-packing-slip.pdf` (same fields: customer, phone, address, method, tracking, notes, lines, totals). The VPS needs cairo/pango/fonts (`install.sh` and each `deploy.sh` install them).

**Schema.** App boot runs Alembic against `DATA_DIR/eshop.db` (`alembic/versions/`). Existing production databases pick up only missing revisions. Do not add new columns in `src/db.py` if-blocks.

## How customers follow an order

There is no customer login and no public “track my order” form.

After checkout they get:

1. A thank-you page with **View order details**
2. A confirmation email with the same private link: `https://print-me-maybe.com/order/…`

They refresh that page to see status changes you save in admin (In progress, Ready to ship, Shipped, Cancelled) and the tracking number when you add one. They get email for:

- the original confirmation
- **Ready** (once, when you first mark Ready to ship)
- **Shipped** / collect-at-studio (pickup when you mark Shipped; delivery only when a tracking number is saved)
- **Cancelled** (when you cancel; refund wording only if Stripe actually refunded on that save)

If they lose the email, copy the customer link or resend confirmation from the order page.

## Payments and refunds

Card checkout uses Stripe Checkout (EUR). **Cash at pick up** never calls Stripe. Production webhook: `https://print-me-maybe.com/webhooks/stripe` for `checkout.session.completed`. Secret: `STRIPE_WEBHOOK_SECRET` in `/etc/eshop.env`.

**EEA cards** are typically **1.5% + €0.25** with no monthly Stripe fee.

| What you do | Customer | Stripe fee |
|-------------|----------|------------|
| Paid order | Charged the full total | You pay the processing fee |
| Cancel in admin (card paid) | Full amount refunded to the original card | **Original fee is not returned** |
| Cancel cash/bank paid | Refund in person | Nothing |
| Cancel unpaid cash-at-pick-up | Nothing charged | Nothing |

There is no extra Stripe fee for issuing a **card** refund on standard Cyprus pricing. Bank-transfer refunds can have extra fees; this shop takes cards through Checkout.

Refunds use your Stripe balance. If the balance is too low, Stripe may hold the refund until more payments land.

Dashboard: [dashboard.stripe.com](https://dashboard.stripe.com) → the payment for that order is the source of truth for the exact fee.

## Order emails

| Event | Studio inbox (`NOTIFY_EMAIL`) | Customer |
|-------|-------------------------------|----------|
| New paid or unpaid order | Yes (order details, phone, customer notes) | Yes (confirmation + private order link) |
| Marked **Ready** (first time only) | No | Yes (pickup: collect; delivery: packed) |
| Marked **Shipped** (pickup) | No | Yes (collect at studio) |
| Marked **Shipped** (delivery) or tracking added later | No | Yes, **only if a tracking number is saved** |
| **Cancelled** | Yes | Yes (refund notice only when a card payment was returned on that save) |
| Paid Stripe session could not create an order | Yes | No (refund is attempted; studio must follow up) |
| Blocked login / checkout flood | Yes (at most once per hour per type) | No |
| **Send test email** in admin | Yes | No |
| **Resend confirmation** / **Resend shipped** | Yes (confirmation also hits studio) | Yes |

Checkout still succeeds if mail fails. New checkouts and attack alerts go to **dimitrioupanagiotis@outlook.com**.

### What you cannot add in Resend → Domains

These names are not yours. Verification will fail:

- `print-me-maybe.onrender.com` / `onrender.com` — Render’s web address (old shop only)
- `outlook.com` — belongs to Microsoft (Outlook can still *receive*)
- `resend.dev` / `example.com` / `beth.t@example.com` — Resend shared test sender
- `@print.me.maybe` — Instagram, not a domain

A domain is a name you **buy** — this project uses **`print-me-maybe.com`**. Mail will send as `orders@print-me-maybe.com` and can still land in Outlook.

### Resend setup for `print-me-maybe.com`

1. [resend.com/domains](https://resend.com/domains) → **Add Domain** → `print-me-maybe.com` (no `https://`).
2. Copy every DNS record Resend shows (TXT / MX) into your DNS provider. Save. Do not skip rows.
3. Wait until Resend shows **Verified**.
4. On the server, set `RESEND_FROM` to `Print Me Maybe <orders@print-me-maybe.com>` in `/etc/eshop.env`.
5. Confirm `NOTIFY_EMAIL` is `dimitrioupanagiotis@outlook.com`.
6. `systemctl restart eshop`
7. Studio **Orders** → **Send test email**.
8. Resend **Emails → Sending** and **Logs** (not **Receiving**): **Delivered**, not 403.
9. Outlook: search Inbox, Junk, Other, Focused. Mark Not junk the first time.

Attack alerts (blocked studio login or checkout flood) email at most once per hour per type.

## Security

- `ENV=production` refuses to boot without `SESSION_SECRET` and `ADMIN_PASSWORD`
- Session cookies: `SameSite=lax`, HTTPS-only in production
- Studio password compared with SHA-256 + `hmac.compare_digest` (failed logins are logged, never the password)
- Security headers: `nosniff`, `DENY` framing, Referrer-Policy, Permissions-Policy, CSP, HSTS on HTTPS
- Customer orders use `lookup_token`, not sequential public URLs
- `/etc/eshop.env` is mode `640`, owned by `root:eshop`

Rate limits (in-memory, per instance, by IP):

| Action | Default |
|--------|---------|
| Pages | 240 / minute |
| Studio login POST | 5 / 15 minutes |
| Checkout POST | 12 / hour |
| Cart POST | 60 / minute |

`/health`, `/static/`, `/media/`, `/webhooks/` are exempt. HTTP 429 includes `Retry-After`.

## Backups

SQLite lives at `/var/lib/eshop/eshop.db`. `install.sh` and `deploy.sh` install a root cron job that runs at **03:15 UTC**:

```bash
15 3 * * * /opt/eshop/deploy/backup.sh >> /var/lib/eshop/backups/cron.log 2>&1
```

Copies older than 14 days are deleted. Copy a backup off the server occasionally (`scp`) or enable a Hetzner snapshot (extra cost). Reboot the VPS after a test order and confirm studio still shows it.

## License

[MIT](LICENSE) — use freely for learning and demos.
