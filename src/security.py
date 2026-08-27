"""Production secrets, session flags, studio path, CSRF, and browser headers."""

from __future__ import annotations

import hmac
import os
import secrets
import time

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

CSP = (
    "default-src 'self'; "
    "img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; "
    "script-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self' https://checkout.stripe.com https://pay.stripe.com; "
    "frame-ancestors 'none'"
)


def production_mode() -> bool:
    """True on Render or when ENV=production."""
    if os.environ.get("RENDER"):
        return True
    return os.environ.get("ENV", "").strip().lower() == "production"


def session_secret() -> str:
    secret = os.environ.get("SESSION_SECRET", "").strip()
    if production_mode() and not secret:
        raise RuntimeError("SESSION_SECRET is required in production")
    return secret or "dev-only-change-me-in-production"


def session_https_only() -> bool:
    raw = os.environ.get("SESSION_HTTPS_ONLY", "").strip().lower()
    if raw in {"1", "true", "yes"}:
        return True
    if raw in {"0", "false", "no"}:
        return False
    return production_mode()


DEFAULT_STUDIO_PATH = "/studio"
ADMIN_SESSION_DEFAULT_HOURS = 8
_RESERVED_STUDIO_PREFIXES = {
    "cart",
    "checkout",
    "product",
    "order",
    "health",
    "static",
    "media",
    "webhooks",
    "api",
    "privacy",
    "pay",
    "robots.txt",
    "sitemap.xml",
    "login",
}


def studio_path() -> str:
    """URL prefix for studio. Default /studio; override with ADMIN_PATH."""
    raw = os.environ.get("ADMIN_PATH", DEFAULT_STUDIO_PATH).strip() or DEFAULT_STUDIO_PATH
    if not raw.startswith("/"):
        raw = "/" + raw
    parts = [part for part in raw.split("/") if part]
    if not parts or parts[0].lower() in _RESERVED_STUDIO_PREFIXES:
        return DEFAULT_STUDIO_PATH
    return "/" + "/".join(parts)


def studio_url(suffix: str = "", query: str = "") -> str:
    """Build a studio path such as /studio/orders?status=new."""
    path = studio_path()
    extra = (suffix or "").strip()
    if extra:
        if not extra.startswith("/"):
            extra = "/" + extra
        path = f"{path}{extra}"
    if query:
        path = f"{path}?{query.lstrip('?')}"
    return path


def csrf_protection_disabled() -> bool:
    return os.environ.get("CSRF_DISABLED", "").strip().lower() in {"1", "true", "yes"}


def issue_csrf_token(request: Request) -> str:
    """Return the session CSRF token, creating one if needed."""
    try:
        session = request.session
    except AssertionError:
        return ""
    token = session.get("csrf_token")
    if not isinstance(token, str) or len(token) < 16:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


async def verify_studio_csrf(request: Request) -> None:
    """Require a CSRF token on studio POST/PUT/PATCH/DELETE."""
    if request.method in {"GET", "HEAD", "OPTIONS", "TRACE"}:
        return
    if csrf_protection_disabled():
        return
    expected = request.session.get("csrf_token")
    token = (request.headers.get("x-csrf-token") or "").strip()
    if not token:
        content_type = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            form = await request.form()
            token = str(form.get("csrf_token") or "")
    if not expected or not token or not hmac.compare_digest(str(expected), token):
        raise HTTPException(status_code=403, detail="CSRF check failed")


def admin_session_seconds() -> int:
    raw = os.environ.get("ADMIN_SESSION_HOURS", "").strip()
    try:
        hours = float(raw) if raw else ADMIN_SESSION_DEFAULT_HOURS
    except ValueError:
        hours = ADMIN_SESSION_DEFAULT_HOURS
    return max(60, int(hours * 3600))


def studio_is_admin(session: dict) -> bool:
    if not session.get("is_admin"):
        return False
    started = session.get("admin_at")
    if not isinstance(started, (int, float)):
        return False
    return (time.time() - float(started)) <= admin_session_seconds()


def mark_studio_login(session: dict) -> None:
    session["is_admin"] = True
    session["admin_at"] = time.time()


def clear_studio_login(session: dict) -> None:
    session.pop("is_admin", None)
    session.pop("admin_at", None)


def require_production_secrets() -> None:
    """Refuse to boot on Render without real session and admin secrets."""
    if not production_mode():
        return
    if not os.environ.get("SESSION_SECRET", "").strip():
        raise RuntimeError("SESSION_SECRET is required in production")
    if not os.environ.get("ADMIN_PASSWORD", "").strip():
        raise RuntimeError("ADMIN_PASSWORD is required in production")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Content-Security-Policy", CSP)
        forwarded = request.headers.get("x-forwarded-proto", "")
        if request.url.scheme == "https" or forwarded.split(",")[0].strip() == "https":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response
