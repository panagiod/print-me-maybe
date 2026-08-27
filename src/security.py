"""Production secrets, session flags, and browser security headers."""

from __future__ import annotations

import os

from fastapi import Request
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
