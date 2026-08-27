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
- [CI/CD deployment](#cicd-deployment)
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
4. **Install** — [#5](https://github.com/panagiod/print-me-maybe/issues/5) SSH as root (one-time bootstrap):

   ```bash
   git clone https://github.com/panagiod/print-me-maybe.git /opt/eshop
   bash /opt/eshop/deploy/install.sh
   ```

   Then set up [CI/CD](#cicd-deployment) so every push to `main` deploys automatically.

   Manual update anytime: `bash /opt/eshop/deploy/deploy.sh`

   `install.sh` generates `SESSION_SECRET` and `ADMIN_PASSWORD` and prints the admin password once. Caddy gets HTTPS automatically after DNS points at the server.
5. **Stripe** — [#6](https://github.com/panagiod/print-me-maybe/issues/6) [dashboard.stripe.com](https://dashboard.stripe.com) → activate payments, EUR, copy the **secret** key into `STRIPE_SECRET_KEY`. Add a webhook endpoint `https://print-me-maybe.com/webhooks/stripe` for `checkout.session.completed` and put the signing secret in `STRIPE_WEBHOOK_SECRET`. Checkout redirects to Stripe; the order is created from the webhook (or `/pay/success`) only after `payment_status=paid`.
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
- Studio at `/admin` (not linked in public nav): orders, notes, cancel (refund + restock + customer email), add/remove product + photo
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
  admin.py           Studio login, orders, stock, add/edit/remove product, test email
  store.py           Products, cart lines, place_order, pending Stripe checkouts
  db.py              SQLite schema and DATA_DIR
  models.py          Product/Order types, EUR formatting, shipping rules
  seed.py            Catalog copied from Instagram listings
  payments.py        Stripe Checkout, webhooks, refunds
  fulfill.py         Paid Stripe session → order (idempotent)
  notify.py          Resend/SMTP mail, attack alerts, customer confirmation
  ratelimit.py       Per-IP limits
  security.py        Secrets, HTTPS cookies, CSP/HSTS
  uploads.py         Admin product photos
templates/           HTML (base, shop, cart, checkout, admin)
static/              CSS and seed product images
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

GitHub Actions (`.github/workflows/ci.yml`) runs on every pull request and on push to `main`: install deps, pytest, then boot Uvicorn and `curl` `/health` and `/`.

Shop tests cover pick-up (free), Cyprus delivery (€3.50), international delivery (€10), and studio product delete (including the block when a product has already been ordered).

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

**Catalog.** Seed SKUs live in `src/seed.py` (names, euro prices, photos from public Instagram where a price was named). On boot, seed rows are upserted **by slug**. Stock changes and products added in studio are kept; seed does not reset quantity.

**Cart.** Stored in the signed session cookie (7 days). Add/update quantity is capped at remaining stock. Zero stock hides a product from the shop. The cart shows the product subtotal only; shipping is not applied until checkout.

**Checkout.** GET `/checkout` collects name, email, and a delivery choice (pick up vs ship). Delivery requires a destination (Cyprus or outside Cyprus) and an address. POST `/checkout` then:

1. Recalculates shipping from the chosen method and destination (see [Shipping](#shipping)).
2. If Stripe is configured, the browser goes to Stripe Checkout. Shipping is a separate Stripe line item when it is more than €0. The cart, shipping method, destination, unit prices, and totals are stored in SQLite (`pending_checkouts`) keyed by the Stripe session id (Stripe metadata is a backup). The order is created when Stripe sends `checkout.session.completed` to `POST /webhooks/stripe`, or when the customer lands on `GET /pay/success`. Both paths are idempotent.
3. If creating the order fails after payment (for example stock ran out), the shop refunds the PaymentIntent and emails the studio.
4. Without Stripe, checkout is the no-card demo and still stores the same total (subtotal + shipping).

Pick-up orders store method `pickup` and address `Pick up at studio`. Delivery orders store `shipping_method`, `delivery_country` (`cyprus` or `other`), and the typed address.

**Customer order URL.** `/order/{lookup_token}` — random token, not the numeric id. Confirmation, order pages, and emails show the shipping method label plus Free / €3.50 / €10.

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
- The `orders` table stores `shipping_method`, `delivery_country`, `shipping_address`, and a combined `total_cents` (subtotal + shipping). Shipping itself is also derived as `total_cents − item subtotal`.

## Studio admin

Public nav does not advertise `/admin`. Login: `/admin/login` on your domain.

| Page | What it does |
|------|----------------|
| `/admin/orders` | Filter by status; Paid / Unpaid / Refunded; **Send test email** |
| `/admin/orders/{id}` | Status, tracking number, notes, cancel (Stripe refund if paid, restock, email customer) / reopen (deduct stock; does not charge again) |
| `/admin/stock` | Add product; **Edit** name/price/description/category/photo/qty; set stock; **Remove** unused products |

**Remove a product.** Each row on `/admin/stock` has a **Remove** button (`POST /admin/products/{id}/delete`). Deletion is a hard delete from the `products` table. It is **blocked** if that product appears on any past order (foreign key on `order_items`). In that case the studio sees: *This product has been ordered before. Set stock to 0 to hide it from the shop.* Setting stock to 0 still hides the item from the public catalog without deleting history.

Order statuses: New → In progress → Ready to ship → Shipped, plus Cancelled.

**Cancel a paid order** from that order page. The shop refunds the Stripe Checkout payment first; if Stripe rejects the refund, the order stays open and stock is not put back. After a successful refund the payment pill shows **Refunded**, items return to stock, and the customer (and studio inbox) get a cancellation email. Unpaid demo orders skip Stripe and still email the customer. Reopening a cancelled order deducts stock again and does **not** charge the card.

**Tracking number.** On the same order page, paste the courier number in **Tracking number** when you set status to **Shipped**. It is stored on the order, shown on the customer’s `/order/{token}` page, and included in a shipped email. You can add the number later; saving a new tracking number on an already-shipped order emails the customer again. Leave it blank for pick-up.

Uploaded photos are served from `/media/products/...` and stored under `DATA_DIR/product-images`.

## Order emails

New checkouts and blocked login/checkout floods email **dimitrioupanagiotis@outlook.com**. Checkout still succeeds if mail fails. Cancelling an order from studio admin also emails the customer (refund notice when a card payment was returned). Marking an order **Shipped** emails the customer the tracking number when you added one.

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
