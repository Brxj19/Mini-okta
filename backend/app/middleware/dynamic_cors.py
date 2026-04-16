"""Dynamic CORS middleware based on registered application redirect URIs."""

from __future__ import annotations

import asyncio
import time
from typing import Iterable
from urllib.parse import urlparse

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import PlainTextResponse
from sqlalchemy import select

from app.config import settings
from app.database import async_session_factory
from app.models.application import Application


DEFAULT_ALLOWED_ORIGINS = {
    settings.ADMIN_CONSOLE_URL.rstrip("/"),
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:4000",
    "http://localhost:4001",
    "http://localhost:4101",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://127.0.0.1:5175",
}


def _origin_from_uri(uri: str | None) -> str | None:
    """Return scheme://host[:port] for a valid HTTP(S) URI."""
    if not uri:
        return None

    parsed = urlparse(uri)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    return f"{parsed.scheme}://{parsed.netloc}"


def _append_vary(existing: str | None, value: str) -> str:
    if not existing:
        return value
    parts = [item.strip() for item in existing.split(",") if item.strip()]
    if value in parts:
        return existing
    return f"{existing}, {value}"


class DynamicCORSMiddleware:
    """CORS middleware that derives trusted origins from registered apps."""

    def __init__(
        self,
        app,
        *,
        allow_credentials: bool = True,
        allow_methods: Iterable[str] | None = None,
        expose_headers: Iterable[str] | None = None,
        refresh_interval_seconds: int = 30,
    ):
        self.app = app
        self.allow_credentials = allow_credentials
        self.allow_methods = ", ".join(allow_methods or ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
        self.expose_headers = ", ".join(expose_headers or ["*"])
        self.refresh_interval_seconds = refresh_interval_seconds
        self._cached_origins = set(DEFAULT_ALLOWED_ORIGINS)
        self._last_refresh = 0.0
        self._refresh_lock = asyncio.Lock()

    async def _load_registered_origins(self) -> set[str]:
        origins = set(DEFAULT_ALLOWED_ORIGINS)

        async with async_session_factory() as session:
            result = await session.execute(select(Application.redirect_uris))
            redirect_uri_lists = result.scalars().all()

        for redirect_uris in redirect_uri_lists:
            for uri in redirect_uris or []:
                origin = _origin_from_uri(uri)
                if origin:
                    origins.add(origin)

        return origins

    async def _get_allowed_origins(self) -> set[str]:
        now = time.monotonic()
        if self._cached_origins and now - self._last_refresh < self.refresh_interval_seconds:
            return self._cached_origins

        async with self._refresh_lock:
            now = time.monotonic()
            if self._cached_origins and now - self._last_refresh < self.refresh_interval_seconds:
                return self._cached_origins

            self._cached_origins = await self._load_registered_origins()
            self._last_refresh = now
            return self._cached_origins

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        origin = headers.get("origin")
        if not origin:
            await self.app(scope, receive, send)
            return

        allowed_origins = await self._get_allowed_origins()
        is_allowed = origin.rstrip("/") in allowed_origins

        if scope["method"] == "OPTIONS" and headers.get("access-control-request-method"):
            if not is_allowed:
                response = PlainTextResponse("CORS origin denied", status_code=400)
                await response(scope, receive, send)
                return

            response = PlainTextResponse("", status_code=204)
            self._apply_cors_headers(response.headers, origin, headers)
            await response(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start" and is_allowed:
                mutable_headers = MutableHeaders(scope=message)
                self._apply_cors_headers(mutable_headers, origin, headers)
            await send(message)

        await self.app(scope, receive, send_wrapper)

    def _apply_cors_headers(self, headers: MutableHeaders, origin: str, request_headers: Headers) -> None:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Methods"] = self.allow_methods
        headers["Access-Control-Expose-Headers"] = self.expose_headers
        headers["Vary"] = _append_vary(headers.get("Vary"), "Origin")

        requested_headers = request_headers.get("access-control-request-headers")
        headers["Access-Control-Allow-Headers"] = requested_headers or "*"

        if self.allow_credentials:
            headers["Access-Control-Allow-Credentials"] = "true"
