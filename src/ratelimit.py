"""In-memory per-IP rate limits for login, checkout, and request floods."""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from pathlib import Path
from threading import Lock

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from src.security import issue_csrf_token, studio_path, studio_url

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["studio_path"] = studio_path()
templates.env.globals["csrf_token"] = issue_csrf_token

EXEMPT_PREFIXES = ("/health", "/static/", "/media/", "/webhooks/")


class RateLimiter:
    """Sliding-window counters. Fine for a single Render instance."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def reset(self) -> None:
        with self._lock:
            self._events.clear()

    def hit(self, key: str, max_hits: int, window_seconds: int) -> tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            q = self._events[key]
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= max_hits:
                retry = int(q[0] + window_seconds - now) + 1
                return False, max(1, retry)
            q.append(now)
            if not q:
                self._events.pop(key, None)
            return True, 0


limiter = RateLimiter()


def rate_limit_disabled() -> bool:
    return os.environ.get("RATE_LIMIT_DISABLED", "").lower() in {"1", "true", "yes"}


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _rules(method: str, path: str) -> list[tuple[str, int, int]]:
    """Return (bucket, max_hits, window_seconds) that apply to this request."""
    rules: list[tuple[str, int, int]] = [
        ("ip", _int_env("RATE_LIMIT_IP", 240), 60),
    ]
    if method != "POST":
        return rules
    login_path = studio_url("/login")
    studio_prefix = studio_path().rstrip("/") + "/"
    if path == login_path:
        rules.append(("login", _int_env("RATE_LIMIT_LOGIN", 5), _int_env("RATE_LIMIT_LOGIN_WINDOW", 900)))
    elif path == "/checkout":
        rules.append(("checkout", _int_env("RATE_LIMIT_CHECKOUT", 12), _int_env("RATE_LIMIT_CHECKOUT_WINDOW", 3600)))
    elif path.startswith("/cart/"):
        rules.append(("cart", _int_env("RATE_LIMIT_CART", 60), 60))
    elif path == studio_path() or path.startswith(studio_prefix):
        rules.append(("admin", _int_env("RATE_LIMIT_ADMIN", 60), 60))
    else:
        rules.append(("write", _int_env("RATE_LIMIT_WRITE", 60), 60))
    return rules


def _shop_name() -> str:
    return os.environ.get("SHOP_NAME", "Print Me Maybe")


def rate_limited_response(request: Request, retry_after: int) -> Response:
    headers = {"Retry-After": str(retry_after), "Cache-Control": "no-store"}
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            {"detail": "Too many requests"},
            status_code=429,
            headers=headers,
        )
    if request.url.path == studio_url("/login"):
        return templates.TemplateResponse(
            request,
            "admin_login.html",
            {
                "shop_name": _shop_name(),
                "cart_count": 0,
                "is_admin": False,
                "error": "Too many attempts. Try again in a few minutes.",
            },
            status_code=429,
            headers=headers,
        )
    return templates.TemplateResponse(
        request,
        "rate_limited.html",
        {"shop_name": _shop_name(), "cart_count": 0, "is_admin": False},
        status_code=429,
        headers=headers,
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if rate_limit_disabled() or path == "/health" or path.startswith(EXEMPT_PREFIXES):
            return await call_next(request)

        ip = client_ip(request)
        for bucket, max_hits, window in _rules(request.method, path):
            allowed, retry_after = limiter.hit(f"{bucket}:{ip}", max_hits, window)
            if not allowed:
                if bucket in {"login", "checkout"}:
                    from src.notify import notify_attack

                    notify_attack(bucket, ip)
                return rate_limited_response(request, retry_after)
        return await call_next(request)
