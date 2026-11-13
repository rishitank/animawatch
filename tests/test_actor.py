"""Tests for the Apify Actor entry point.

Unit tests cover input handling, the readiness probe and hosted configuration.
The end-to-end test starts the real Actor process (Apify SDK in local
pay-per-event test mode, real Chromium), connects an MCP client to ``/mcp``,
and checks the tools offered, a measurement, the charge and the spending limit.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from animawatch import actor
from animawatch.config import DEFAULT_GEMINI_MODEL, settings

ACTOR_DIR = Path(__file__).parent.parent / ".actor"


@pytest.fixture
def restore_settings() -> Iterator[None]:
    saved = settings.model_dump()
    yield
    for key, value in saved.items():
        setattr(settings, key, value)


class TestApplyActorInput:
    def test_key_turns_vision_on(self, restore_settings: None) -> None:
        settings.gemini_api_key = ""
        actor.apply_actor_input({"geminiApiKey": "  k-123  ", "visionModel": "gemini-x"})
        assert settings.gemini_api_key == "k-123"
        assert settings.vision_provider == "gemini"
        assert settings.vision_model == "gemini-x"
        assert settings.allow_file_urls is False
        assert settings.hosted is True
        assert settings.browser_headless is True

    def test_no_key_turns_vision_off(self, restore_settings: None) -> None:
        settings.gemini_api_key = ""
        actor.apply_actor_input(None)
        assert settings.vision_provider == "none"
        assert settings.allow_file_urls is False

    def test_environment_key_is_used(self, restore_settings: None) -> None:
        settings.gemini_api_key = "from-env"
        actor.apply_actor_input({})
        assert settings.vision_provider == "gemini"

    def test_vision_off_drops_the_key(self, restore_settings: None) -> None:
        actor.apply_actor_input({"geminiApiKey": "k", "visionEnabled": False})
        assert settings.vision_provider == "none"
        assert settings.gemini_api_key == ""  # nothing can reach Gemini

    def test_max_wait_is_applied(self, restore_settings: None) -> None:
        actor.apply_actor_input({"maxWaitSeconds": 10})
        assert settings.max_recording_duration == 10

    @pytest.mark.parametrize(
        "bad",
        [
            {"maxWaitSeconds": 0},
            {"maxWaitSeconds": 500},
            {"maxWaitSeconds": True},
            {"maxWaitSeconds": "10"},
            {"geminiApiKey": 123},
            {"visionModel": ""},
            {"visionEnabled": "yes"},
        ],
    )
    def test_invalid_input_is_rejected_before_any_change(
        self, restore_settings: None, bad: dict[str, object]
    ) -> None:
        settings.max_recording_duration = 30
        settings.allow_file_urls = True
        with pytest.raises(ValidationError):
            actor.apply_actor_input(bad)
        assert settings.max_recording_duration == 30
        assert settings.allow_file_urls is True


class TestReadinessProbe:
    async def _call(self, path: str, headers: list[tuple[bytes, bytes]]) -> list[dict[str, Any]]:
        sent: list[dict[str, Any]] = []
        reached: list[str] = []

        async def inner(scope: Any, receive: Any, send: Any) -> None:
            reached.append(scope["path"])

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b""}

        async def send(message: Any) -> None:
            sent.append(message)

        app = actor.with_readiness_probe(inner)
        await app({"type": "http", "path": path, "headers": headers}, receive, send)
        if reached:
            sent.append({"reached": reached[0]})
        return sent

    async def test_probe_answers_ok(self) -> None:
        sent = await self._call("/", [(actor.READINESS_HEADER, b"1")])
        assert sent[0]["status"] == 200
        assert sent[1]["body"] == b"ok"

    async def test_plain_get_explains_endpoint(self) -> None:
        sent = await self._call("/", [])
        assert b"/mcp" in sent[1]["body"]

    async def test_other_paths_reach_the_app(self) -> None:
        assert await self._call("/mcp", []) == [{"reached": "/mcp"}]


class FakeChargingManager:
    """The part of apify's ChargingManager that ApifyMeter uses."""

    def __init__(self, remaining: int | None) -> None:
        self.remaining = remaining
        self.asked: list[str] = []

    def calculate_max_event_charge_count_within_limit(self, event_name: str) -> int | None:
        self.asked.append(event_name)
        return self.remaining


class TestApifyMeter:
    class FakeActor:
        def __init__(self, remaining: int | None) -> None:
            self.manager = FakeChargingManager(remaining)
            self.charges: list[tuple[str, int]] = []

        def get_charging_manager(self) -> FakeChargingManager:
            return self.manager

        async def charge(self, event_name: str, count: int) -> None:
            self.charges.append((event_name, count))

    async def test_remaining_and_charge(self) -> None:
        fake = self.FakeActor(remaining=3)
        meter = actor.ApifyMeter(fake)
        assert await meter.remaining("page-analysed") == 3
        assert fake.manager.asked == ["page-analysed"]
        await meter.charge("page-analysed", 2)
        assert fake.charges == [("page-analysed", 2)]

    async def test_unlimited(self) -> None:
        assert await actor.ApifyMeter(self.FakeActor(remaining=None)).remaining("x") is None


class TestHostedServer:
    async def test_local_file_tools_removed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from animawatch import server

        for name in ("transport_security", "streamable_http_path", "session_idle_timeout"):
            monkeypatch.setattr(server.mcp.settings, name, getattr(server.mcp.settings, name))
        try:
            actor.configure_hosted_server()
            actor.configure_hosted_server()  # idempotent
            names = {t.name for t in await server.mcp.list_tools()}
            assert names.isdisjoint(actor.HOSTED_DISABLED_TOOLS)
            assert {"watch", "analyze_fps", "screenshot"} <= names
            assert server.mcp.settings.streamable_http_path == "/mcp"
        finally:
            # Put the tools back through the public API for the other tests.
            for tool in (server.analyze_video, server.record, server.analyze_with_consensus_tool):
                server.mcp.add_tool(tool)
        assert set(actor.HOSTED_DISABLED_TOOLS) <= {t.name for t in await server.mcp.list_tools()}

    def test_port(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class Config:
            web_server_port = 4444

        class WithPort:
            configuration = Config()

        class NoPort:
            configuration = object()

        assert actor.web_server_port(WithPort()) == 4444
        monkeypatch.setenv("ACTOR_WEB_SERVER_PORT", "5555")
        assert actor.web_server_port(NoPort()) == 5555


class TestActorDefinition:
    def test_actor_json(self) -> None:
        spec = json.loads((ACTOR_DIR / "actor.json").read_text())
        assert spec["actorSpecification"] == 1
        assert spec["usesStandbyMode"] is True
        assert spec["webServerMcpPath"] == actor.MCP_PATH
        assert (ACTOR_DIR / spec["input"]).exists()
        assert (ACTOR_DIR / spec["dockerfile"]).exists()
        assert (ACTOR_DIR / spec["readme"]).exists()

    def test_input_schema_key_is_secret(self) -> None:
        schema = json.loads((ACTOR_DIR / "input_schema.json").read_text())
        key = schema["properties"]["geminiApiKey"]
        assert key["isSecret"] is True
        assert key["type"] == "string"
        assert key["editor"] == "textfield"
        assert schema["properties"]["visionModel"]["default"] == DEFAULT_GEMINI_MODEL

    def test_dockerfile_uses_apify_playwright_python_image(self) -> None:
        dockerfile = (ACTOR_DIR.parent / "Dockerfile").read_text()
        assert "FROM apify/actor-python-playwright:" in dockerfile
        assert 'CMD ["animawatch-actor"]' in dockerfile


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.browser
async def test_actor_end_to_end(tmp_path: Path, page_server: str) -> None:
    pytest.importorskip("apify", reason="needs the Apify SDK: uv pip install 'apify>=4.0.0,<5'")
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    storage = tmp_path / "storage"
    input_dir = storage / "key_value_stores" / "default"
    input_dir.mkdir(parents=True)
    (input_dir / "INPUT.json").write_text(json.dumps({"visionEnabled": False}))

    port = _free_port()
    env = {
        **os.environ,
        "ACTOR_WEB_SERVER_PORT": str(port),
        "ACTOR_TEST_PAY_PER_EVENT": "true",
        # Locally an event with no price costs $1, so $1 allows exactly one page.
        "ACTOR_MAX_TOTAL_CHARGE_USD": "1",
        "APIFY_LOCAL_STORAGE_DIR": str(storage),
        "CRAWLEE_STORAGE_DIR": str(storage),
        "CRAWLEE_PURGE_ON_START": "false",
        "GEMINI_API_KEY": "",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "animawatch.actor"],
        env=env,
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 60
        while True:
            try:
                probe = httpx.get(
                    base + "/", headers={actor.READINESS_HEADER.decode(): "1"}, timeout=2
                )
                if probe.status_code == 200:
                    break
            except httpx.HTTPError:
                pass  # not listening yet: retry until the deadline
            if proc.poll() is not None or time.monotonic() > deadline:
                # Stop the child first: reading its pipe while it runs would block.
                proc.terminate()
                try:
                    output, _ = proc.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    output, _ = proc.communicate(timeout=10)
                pytest.fail(f"Actor did not become ready:\n{output.decode(errors='replace')}")
            time.sleep(0.5)
        assert probe.text == "ok"

        async with (
            streamable_http_client(base + "/mcp") as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            names = {tool.name for tool in (await session.list_tools()).tools}
            assert "analyze_fps" in names
            assert "analyze_video" not in names
            assert "record" not in names

            first = await session.call_tool(
                "analyze_fps", {"url": f"{page_server}/smooth.html", "duration": 1.0}
            )
            text = first.content[0].text  # type: ignore[union-attr]
            assert not first.isError, text
            assert "Verdict**: smooth" in text

            refused = await session.call_tool(
                "analyze_fps", {"url": f"{page_server}/smooth.html", "duration": 1.0}
            )
            assert refused.isError
            assert "spending limit" in refused.content[0].text  # type: ignore[union-attr]

            local = await session.call_tool("screenshot", {"url": "file:///etc/hostname"})
            assert local.isError
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()

    log_dir = storage / "datasets" / "charging-log"
    items = [json.loads(p.read_text()) for p in sorted(log_dir.glob("*.json")) if p.name[0] != "_"]
    charged = [i for i in items if i.get("event_name") == "page-analysed"]
    assert [i["charged_count"] for i in charged] == [1], items
