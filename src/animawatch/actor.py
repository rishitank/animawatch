"""Run AnimaWatch as an Apify Actor in Standby mode (single-tenant).

The Actor serves the MCP server over streamable HTTP at ``/mcp`` on the port
Apify gives it, and answers Apify's readiness probe. It is designed for
single-tenant Standby: each user's server runs in that user's own Apify
account, so the user pays the platform compute, plus the ``page-analysed``
pay-per-event charge. Nothing is shared between users.

Hosted differences from a local install:

- ``file://`` URLs are refused, and the tools that take or return local file
  paths (``analyze_video``, ``record``) are not offered;
- the vision pass uses the key the user supplies in the Actor input
  (``geminiApiKey``, a secret field) or is off; Ollama is not available;
- each page a tool loads and analyses is charged as one ``page-analysed`` event,
  only after the result is ready, and a run past its spending limit refuses work.

Needs the Apify SDK, which the Actor's Dockerfile installs:
``pip install 'apify>=4.0.0,<5'``.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from mcp.server.fastmcp.exceptions import ToolError

from .billing import PAGE_ANALYSED, set_meter
from .config import DEFAULT_GEMINI_MODEL, settings

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

READINESS_HEADER = b"x-apify-container-server-readiness-probe"
MCP_PATH = "/mcp"
#: Tools that read or write local files: meaningless or unsafe when hosted.
HOSTED_DISABLED_TOOLS = ("analyze_video", "record")
#: Idle MCP sessions are closed after this many seconds.
SESSION_IDLE_TIMEOUT_SECONDS = 300


def apply_actor_input(actor_input: dict[str, Any] | None) -> None:
    """Configure vision and limits from the Actor input.

    Input fields (see ``.actor/input_schema.json``): ``geminiApiKey`` (secret),
    ``visionModel``, ``visionEnabled`` and ``maxWaitSeconds``. A key in the
    ``GEMINI_API_KEY`` environment variable is used when the input has none.
    """
    data = actor_input or {}
    key = str(data.get("geminiApiKey") or "").strip()
    if key:
        settings.gemini_api_key = key
    model = str(data.get("visionModel") or "").strip()
    settings.vision_model = model or settings.vision_model or DEFAULT_GEMINI_MODEL

    vision_enabled = data.get("visionEnabled", True)
    if vision_enabled is False or not settings.gemini_api_key:
        settings.vision_provider = "none"
    else:
        settings.vision_provider = "gemini"

    max_wait = data.get("maxWaitSeconds")
    if isinstance(max_wait, int) and not isinstance(max_wait, bool) and 1 <= max_wait <= 120:
        settings.max_recording_duration = max_wait

    settings.allow_file_urls = False
    settings.browser_headless = True


def configure_hosted_server() -> None:
    """Remove local-file tools and set the HTTP transport up for the platform."""
    from .server import mcp

    for name in HOSTED_DISABLED_TOOLS:
        # ToolError: already removed (configured twice).
        with contextlib.suppress(ToolError):
            mcp.remove_tool(name)
    mcp.settings.streamable_http_path = MCP_PATH
    mcp.settings.session_idle_timeout = SESSION_IDLE_TIMEOUT_SECONDS
    # The container is reachable only through Apify's authenticated proxy, whose
    # Host header is the Actor's standby domain. DNS-rebinding protection guards
    # servers on a user's own localhost and would reject the proxy's requests.
    mcp.settings.transport_security = None


def with_readiness_probe(app: ASGIApp) -> ASGIApp:
    """Answer Apify's readiness probe and a plain GET / before the MCP app."""

    async def wrapped(scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") == "http" and scope.get("path") in ("/", ""):
            headers = dict(scope.get("headers") or [])
            body = (
                b"ok"
                if READINESS_HEADER in headers
                else b"AnimaWatch MCP server. Connect an MCP client to /mcp."
            )
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", b"text/plain; charset=utf-8")],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await app(scope, receive, send)

    return wrapped


class ApifyMeter:
    """Charges pay-per-event events through the Apify SDK."""

    def __init__(self, actor: Any) -> None:
        self._actor = actor

    async def remaining(self, event: str) -> int | None:
        manager = self._actor.get_charging_manager()
        result = manager.calculate_max_event_charge_count_within_limit(event)
        return None if result is None else int(result)

    async def charge(self, event: str, count: int) -> None:
        await self._actor.charge(event_name=event, count=count)


def web_server_port(actor: Any) -> int:
    """The port Apify routes the Standby URL to."""
    port = getattr(actor.configuration, "web_server_port", None)
    if port:
        return int(port)
    return int(os.environ.get("ACTOR_WEB_SERVER_PORT", "4321"))


async def run() -> None:
    """Start the Actor: read input, then serve MCP until the platform stops the run."""
    import uvicorn
    from apify import Actor

    async with Actor:
        apply_actor_input(await Actor.get_input())
        set_meter(ApifyMeter(Actor))
        configure_hosted_server()

        from .server import mcp

        app = with_readiness_probe(mcp.streamable_http_app())
        port = web_server_port(Actor)
        Actor.log.info(
            "AnimaWatch MCP server starting",
            extra={
                "port": port,
                "path": MCP_PATH,
                "vision": settings.vision_provider,
                "charged_event": PAGE_ANALYSED,
            },
        )
        config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")  # noqa: S104
        await uvicorn.Server(config).serve()


def main() -> None:
    """Console entry point (``animawatch-actor``)."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
