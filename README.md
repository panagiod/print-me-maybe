# Print Me Maybe (Hetzner)

**Production deployment** of the [Print Me Maybe](https://www.instagram.com/print.me.maybe/) shop on a cheap Hetzner VPS with persistent storage, your own domain, Stripe Checkout, and Resend order emails.

## Purpose

| | |
|---|---|
| **This repo** | [panagiod/print-me-maybe](https://github.com/panagiod/print-me-maybe) — Hetzner VPS, persistent disk, real card payments |
| **Not this repo** | [panagiod/eshop](https://github.com/panagiod/eshop) (`main`) — free Render demo at [print-me-maybe.onrender.com](https://print-me-maybe.onrender.com) |

The two repos share the same Python app but serve different hosts. **Do not merge this tree into `eshop` `main`** — the Render shop stays as-is.

**Why Hetzner?** Orders and product photos live on disk (`/var/lib/eshop`) instead of ephemeral `/tmp` on Render Free. Fixed cost is about **€8/month** (CX23 + VAT) + **~$11/year** for a domain. Stripe charges **1.5% + €0.25** on EEA cards with no monthly fee.

**Status:** application code and `deploy/` scripts are ready. **Domain:** `print-me-maybe.com` (registered). **Go-live work:** [GitHub Issues](https://github.com/panagiod/print-me-maybe/issues).

## Next steps

Work through these issues in order:

1. ~~[#8 Buy a domain](https://github.com/panagiod/print-me-maybe/issues/8)~~ — **done:** `print-me-maybe.com`
2. [#7 Provision Hetzner CX23 VPS](https://github.com/panagiod/print-me-maybe/issues/7)
3. [#3 Point DNS at the Hetzner server](https://github.com/panagiod/print-me-maybe/issues/3)
4. [#5 Deploy the shop on the VPS](https://github.com/panagiod/print-me-maybe/issues/5)
5. [#6 Connect Stripe Checkout](https://github.com/panagiod/print-me-maybe/issues/6)
6. [#2 Verify domain in Resend and configure order emails](https://github.com/panagiod/print-me-maybe/issues/2)
7. [#4 Smoke test: paid order survives a reboot](https://github.com/panagiod/print-me-maybe/issues/4)

## Contents

- [Purpose](#purpose)
- [Next steps](#next-steps)
- [What this project is](#what-this-project-is)
- [Go live (cheapest stack)](#go-live-cheapest-stack)
- [Buy a Hetzner CX23 server](#buy-a-hetzner-cx23-server)
- [Point DNS at the Hetzner server](#point-dns-at-the-hetzner-server)
- [Features](#features)
- [Stack](#stack)
- [Repository layout](#repository-layout)
- [Local development](#local-development)
- [Tests and CI](#tests-and-ci)
- [Configuration](#configuration)
- [Shop behaviour](#shop-behaviour)
- [Shipping](#shipping)
- [Studio admin](#studio-admin)
- [Order emails](#order-emails)
- [Security](#security)
- [Backups](#backups)
- [License](#license)

## What this project is

| This project **does** | This project **does not** |
|-----------------------|---------------------------|
| Keep orders and photos on the Hetzner disk (`/var/lib/eshop`) | Wipe data on sleep (Render Free does that) |
| Take **card payment** via Stripe Checkout when `STRIPE_SECRET_KEY` is set | Charge a monthly Stripe or Shopify fee |
| Email the studio via Resend after you verify **your** domain | Send from `onboarding@resend.dev` or `outlook.com` |

Custom names/files still go over **Instagram DM**.

## Go live (cheapest stack)

Track progress in [Issues](https://github.com/panagiod/print-me-maybe/issues). Summary:

1. **Domain** — **done:** `print-me-maybe.com` ([#8](https://github.com/panagiod/print-me-maybe/issues/8))
2. **Server** — [#7](https://github.com/panagiod/print-me-maybe/issues/7) Hetzner Cloud **CX23** — see [Buy a Hetzner CX23 server](#buy-a-hetzner-cx23-server) below.
3. **DNS** — [#3](https://github.com/panagiod/print-me-maybe/issues/3) — see [Point DNS at the Hetzner server](#point-dns-at-the-hetzner-server) below.
4. **Install** — [#5](https://github.com/panagiod/print-me-maybe/issues/5) SSH as root:

   ```bash
   git clone https://github.com/panagiod/print-me-maybe.git /opt/eshop
   sudo bash /opt/eshop/deploy/install.sh
   nano /etc/eshop.env   # SHOP_URL, Stripe, Resend
   nano /etc/caddy/Caddyfile   # already set to print-me-maybe.com in repo
   systemctl restart eshop
   systemctl reload caddy
   ```

   `install.sh` generates `SESSION_SECRET` and `ADMIN_PASSWORD` and prints the admin password once. Caddy gets HTTPS automatically after DNS points at the server.
5. **Stripe** — [#6](https://github.com/panagiod/print-me-maybe/issues/6) [dashboard.stripe.com](https://dashboard.stripe.com) → activate payments, EUR, copy the **secret** key (`sk_live_…` or `sk_test_…` for a dry run) into `STRIPE_SECRET_KEY`. Checkout redirects to Stripe and only creates the order after `payment_status=paid`.
6. **Resend** — [#2](https://github.com/panagiod/print-me-maybe/issues/2) [resend.com/domains](https://resend.com/domains) → add `print-me-maybe.com` (not `onrender.com`) → paste DNS records → wait for **Verified** → set `RESEND_FROM=Print Me Maybe <orders@print-me-maybe.com>`.
7. **Smoke test** — [#4](https://github.com/panagiod/print-me-maybe/issues/4) Check `https://print-me-maybe.com/health` — `"payments": true`, `"persistent": true`. Place a **test** card order (`ACCT-000015`), reboot the VPS, confirm the order is still in studio.

Until `STRIPE_SECRET_KEY` is set, checkout stays a no-card demo (same as the Render shop).

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

- Catalog with category filter (3D Prints / Laser Engraving)
- Session cart; quantity cannot exceed stock
- Shipping chosen at checkout (see [Shipping](#shipping)): pick up free, Cyprus delivery €3.50, outside Cyprus €10
- Checkout: name, email, pick-up or delivery, then **Stripe Checkout** when `STRIPE_SECRET_KEY` is set
- Customer order page at `/order/{unguessable-token}`
- Studio at `/admin` (not linked in public nav): orders, notes, cancel/restock, add/remove product + photo
- Background order email via [Resend](https://resend.com) (needs a domain you own — see [Order emails](#order-emails))
- JSON catalog at `GET /api/products`
- Liveness at `GET /health` (`mail`, `payments`, `persistent`)

## Stack

- **Python 3.12**, [FastAPI](https://fastapi.tiangolo.com/), Uvicorn
- **Jinja2** HTML templates + `static/css`
- **SQLite** under `DATA_DIR` (local default `/tmp/eshop-data`; production `/var/lib/eshop`)
- Signed **session cookies** for cart and studio login
- GitHub Actions CI: pytest + smoke `curl` of `/health` and home

## Repository layout

```
src/                 FastAPI app
  main.py            Storefront routes (home, product, cart, checkout, health)
  admin.py           Studio login, orders, stock, add/remove product, test email
  store.py           Products, cart lines, place_order
  db.py              SQLite schema and DATA_DIR
  models.py          Product/Order types, EUR formatting, shipping rules
  seed.py            Catalog copied from Instagram listings
  payments.py        Stripe Checkout
  notify.py          Resend/SMTP mail, attack alerts
  ratelimit.py       Per-IP limits
  security.py        Secrets, HTTPS cookies, CSP/HSTS
  uploads.py         Admin product photos
templates/           HTML (base, shop, cart, checkout, admin)
static/              CSS and seed product images
tests/               pytest
deploy/              Hetzner systemd unit, Caddyfile, install.sh, env.example, backup.sh
.github/workflows/ci.yml
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

GitHub Actions (`.github/workflows/ci.yml`) runs on every pull request and on push to `main`: install deps, pytest, then boot Uvicorn and `curl` `/health` and `/`.

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
| `DATA_DIR` | `/tmp/eshop-data` locally; `/var/lib/eshop` in production | SQLite + uploaded photos |
| `NOTIFY_EMAIL` | `dimitrioupanagiotis@outlook.com` | Inbox for order and attack alerts |
| `RESEND_API_KEY` | empty (mail skipped) | Resend API key (`re_…`) |
| `RESEND_FROM` | `Print Me Maybe <beth.t@example.com>` | Must be an address on a **verified** Resend domain |
| `STRIPE_SECRET_KEY` | empty (demo checkout, no card) | Stripe secret key (`sk_test_…` or `sk_live_…`) |
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

**Catalog.** Seed SKUs live in `src/seed.py` (names, euro prices, photos from public Instagram where a price was named). On boot, seed rows are upserted **by slug**. Stock changes and products added in studio are kept; seed does not reset quantity.

**Cart.** Stored in the signed session cookie (7 days). Add/update quantity is capped at remaining stock. Zero stock hides a product from the shop. The cart shows the product subtotal only; shipping is not applied until checkout.

**Checkout.** GET `/checkout` collects name, email, and a delivery choice (pick up vs ship). Delivery requires a destination (Cyprus or outside Cyprus) and an address. POST `/checkout` then:

1. Recalculates shipping from the chosen method and destination (see [Shipping](#shipping)).
2. If Stripe is configured, the browser goes to Stripe Checkout. Shipping is a separate Stripe line item when it is more than €0. The order is created only on `GET /pay/success` after Stripe reports `payment_status=paid`. Cart, shipping method, destination, and totals are stored in Stripe metadata so a lost cookie cannot drop a paid order.
3. Without Stripe, checkout is the no-card demo and still stores the same total (subtotal + shipping).

Pick-up orders store the shipping address as `Pick up at studio`. Delivery orders store the address the customer typed.

**Customer order URL.** `/order/{lookup_token}` — random token, not the numeric id. The confirmation and order pages show the shipping line (Free, €3.50, or €10) plus the total.

## Shipping

Rates are decided at checkout, not from cart size. There is no free-shipping threshold.

| Method | Destination | Charge | Constant in `src/models.py` |
|--------|-------------|--------|-----------------------------|
| Pick up at studio | — | Free | `shipping_cents("pickup")` → `0` |
| Delivery | Cyprus | €3.50 | `CYPRUS_SHIPPING_CENTS = 350` |
| Delivery | Outside Cyprus | €10.00 | `INTERNATIONAL_SHIPPING_CENTS = 1000` |

- Cart copy: “Pick up is free. Cyprus delivery is €3.50. Outside Cyprus is €10.”
- Home hero: “Free pick up; €3.50 delivery in Cyprus; €10 shipping outside Cyprus.”
- Checkout totals update in the browser when the customer switches pick-up / delivery or Cyprus / outside Cyprus. The server recomputes the same numbers on POST (and again from Stripe metadata after payment).
- The `orders` table stores `shipping_address` and a combined `total_cents` (subtotal + shipping). Shipping itself is derived as `total_cents − item subtotal`.

## Studio admin

Public nav does not advertise `/admin`. Login: `/admin/login` on your domain.

| Page | What it does |
|------|----------------|
| `/admin/orders` | Filter by status; Paid/Unpaid; **Send test email** |
| `/admin/orders/{id}` | Status, notes, cancel (restock) / reopen (deduct again) |
| `/admin/stock` | Add product (name, description, EUR price, category, photo, qty); set stock; **Remove** unused products |

**Remove a product.** Each row on `/admin/stock` has a **Remove** button (`POST /admin/products/{id}/delete`). Deletion is a hard delete from the `products` table. It is **blocked** if that product appears on any past order (foreign key on `order_items`). In that case the studio sees: *This product has been ordered before. Set stock to 0 to hide it from the shop.* Setting stock to 0 still hides the item from the public catalog without deleting history.

Order statuses: New → In progress → Ready to ship → Shipped, plus Cancelled.

Uploaded photos are served from `/media/products/...` and stored under `DATA_DIR/product-images`.

## Order emails

New checkouts and blocked login/checkout floods email **dimitrioupanagiotis@outlook.com**. Checkout still succeeds if mail fails.

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

`/health`, `/static/`, `/media/` are exempt. HTTP 429 includes `Retry-After`.

## Backups

SQLite lives at `/var/lib/eshop/eshop.db`. Nightly local copies:

```bash
15 3 * * * /opt/eshop/deploy/backup.sh
```

Copy a backup off the server occasionally (`scp`) or enable a Hetzner snapshot (extra cost). Reboot the VPS after a test order and confirm studio still shows it.

## License

[MIT](LICENSE) — use freely for learning and demos.
