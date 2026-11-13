"""Tests for the usage metering hook."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from animawatch import billing


class FakeMeter:
    def __init__(self, remaining: int | None) -> None:
        self._remaining = remaining
        self.charged: list[tuple[str, int]] = []

    async def remaining(self, event: str) -> int | None:
        return self._remaining

    async def charge(self, event: str, count: int) -> None:
        self.charged.append((event, count))


@pytest.fixture(autouse=True)
def restore_meter() -> Iterator[None]:
    yield
    billing.set_meter(billing.NoopMeter())


async def test_default_meter_allows_everything_and_charges_nothing() -> None:
    assert isinstance(billing.get_meter(), billing.NoopMeter)
    await billing.ensure_can_charge(billing.PAGE_ANALYSED, 1000)
    await billing.charge(billing.PAGE_ANALYSED, 3)


async def test_refuses_when_limit_cannot_cover_the_call() -> None:
    billing.set_meter(FakeMeter(remaining=1))
    await billing.ensure_can_charge(billing.PAGE_ANALYSED, 1)
    with pytest.raises(ToolError, match="allows 1 more 'page-analysed' event"):
        await billing.ensure_can_charge(billing.PAGE_ANALYSED, 2)


async def test_unlimited_meter_never_refuses() -> None:
    billing.set_meter(FakeMeter(remaining=None))
    await billing.ensure_can_charge(billing.PAGE_ANALYSED, 10**6)


async def test_charge_passes_through_and_skips_zero() -> None:
    meter = FakeMeter(remaining=None)
    billing.set_meter(meter)
    await billing.charge(billing.PAGE_ANALYSED, 2)
    await billing.charge(billing.PAGE_ANALYSED, 0)
    assert meter.charged == [("page-analysed", 2)]


def test_event_name_matches_the_actor_pricing_file() -> None:
    import json
    from pathlib import Path

    pricing = json.loads(
        (Path(__file__).parent.parent / ".actor" / "pay_per_event.json").read_text()
    )
    assert list(pricing) == [billing.PAGE_ANALYSED]
    assert pricing[billing.PAGE_ANALYSED]["eventPriceUsd"] == 0.05


async def test_metered_charges_only_on_success() -> None:
    meter = FakeMeter(remaining=None)
    billing.set_meter(meter)

    async with billing.metered(billing.PAGE_ANALYSED, 2):
        assert meter.charged == []  # nothing is charged before the work is done
    assert meter.charged == [("page-analysed", 2)]

    with pytest.raises(RuntimeError):
        async with billing.metered(billing.PAGE_ANALYSED):
            raise RuntimeError("page failed to load")
    assert meter.charged == [("page-analysed", 2)]


async def test_concurrent_calls_cannot_both_take_the_last_event() -> None:
    import asyncio

    billing.set_meter(FakeMeter(remaining=1))
    started = asyncio.Event()
    release = asyncio.Event()

    async def first() -> None:
        async with billing.metered(billing.PAGE_ANALYSED):
            started.set()
            await release.wait()

    task = asyncio.create_task(first())
    await started.wait()
    with pytest.raises(ToolError, match="allows 0 more"):
        async with billing.metered(billing.PAGE_ANALYSED):
            pass
    release.set()
    await task


async def test_failed_call_releases_its_reservation() -> None:
    meter = FakeMeter(remaining=1)
    billing.set_meter(meter)
    with pytest.raises(ValueError):
        async with billing.metered(billing.PAGE_ANALYSED):
            raise ValueError("boom")
    async with billing.metered(billing.PAGE_ANALYSED):
        pass
    assert meter.charged == [("page-analysed", 1)]
