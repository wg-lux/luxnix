from __future__ import annotations

import hmac
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

from .config import settings
from .server import LEGACY_MCP, mcp


class OptionalBearerMiddleware(BaseHTTPMiddleware):
    """Optional static bearer gate.

    Useful for generic MCP clients. For a ChatGPT custom app, OAuth/OIDC or the
    Secure MCP Tunnel is preferable when available. Leave WG_LUX_MCP_BEARER_TOKEN
    unset to disable this middleware's authentication check.
    """

    async def dispatch(self, request: Request, call_next):
        expected = None if settings.oauth_enabled else settings.bearer_token
        if expected and request.url.path.startswith("/mcp"):
            header = request.headers.get("authorization", "")
            supplied = header.removeprefix("Bearer ") if header.startswith("Bearer ") else ""
            if not supplied or not hmac.compare_digest(supplied, expected):
                return Response(status_code=401, headers={"WWW-Authenticate": "Bearer"})
        return await call_next(request)


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "service": "wg-lux-mcp", "mode": "read-only"})


@asynccontextmanager
async def lifespan(_: Starlette) -> AsyncIterator[None]:
    async with mcp.session_manager.run():
        yield


security = TransportSecuritySettings(
    allowed_hosts=[
        settings.public_host,
        f"{settings.public_host}:*",
        "127.0.0.1:*",
        "localhost:*",
    ],
    allowed_origins=[
        f"https://{settings.public_host}",
        "http://127.0.0.1:*",
        "http://localhost:*",
    ],
)

if LEGACY_MCP:
    # MCP 1.x configures HTTP transport on FastMCP.settings.
    legacy_settings: Any = mcp.settings
    legacy_settings.streamable_http_path = "/"
    legacy_settings.transport_security = security
    mcp_app = mcp.streamable_http_app()
else:
    # MCP 2.x accepts transport configuration when constructing the ASGI app.
    mcp_app = mcp.streamable_http_app(
        streamable_http_path="/",
        transport_security=security,
    )

app = Starlette(
    routes=[
        Route("/healthz", health, methods=["GET"]),
        Mount("/mcp", app=mcp_app),
    ],
    middleware=[Middleware(OptionalBearerMiddleware)],
    lifespan=lifespan,
)


def main() -> None:
    """Run the local HTTP server using the configured bind address and port."""
    import uvicorn

    uvicorn.run(
        "wg_lux_mcp.asgi:app",
        host=settings.host,
        port=settings.port,
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
    )
