"""Usage metering hook.

Locally nothing is metered. When AnimaWatch runs as an Apify Actor with
pay-per-event pricing, ``animawatch.actor`` installs a meter that charges the
``page-analysed`` event once for each page a tool loads and analyses.

Tools wrap their work in :func:`metered`. It reserves the events before any
page is loaded, so a run that has reached the user's spending limit refuses
work instead of doing it for free (concurrent calls cannot both claim the last
event). It charges only when the work finished without an exception, and
releases the reservation otherwise. If the charge itself fails, the failure is
logged and the finished result is still returned.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol

from mcp.server.fastmcp.exceptions import ToolError

from .logging import log_extra

#: Event name, matching ``.actor/pay_per_event.json``.
PAGE_ANALYSED = "page-analysed"


class UsageMeter(Protocol):
    """Something that can tell whether an event is affordable and charge it."""

    async def remaining(self, event: str) -> int | None:
        """How many more of ``event`` may be charged; None means unlimited."""

    async def charge(self, event: str, count: int) -> None:
        """Charge ``count`` occurrences of ``event``."""


class NoopMeter:
    """The default: nothing is metered."""

    async def remaining(self, event: str) -> int | None:
        return None

    async def charge(self, event: str, count: int) -> None:
        return None


_meter: UsageMeter = NoopMeter()
_reserved: Counter[str] = Counter()
_lock = asyncio.Lock()


def set_meter(meter: UsageMeter) -> None:
    """Install the meter used by every tool (and drop any reservations)."""
    global _meter
    _meter = meter
    _reserved.clear()


def get_meter() -> UsageMeter:
    """The meter currently installed."""
    return _meter


async def ensure_can_charge(event: str, count: int = 1) -> None:
    """Raise ToolError if the run's spending limit cannot cover ``count`` more events.

    Events reserved by calls still in progress count as spent.
    """
    remaining = await _meter.remaining(event)
    if remaining is None:
        return
    available = remaining - _reserved[event]
    if available < count:
        raise ToolError(
            f"The spending limit for this run is reached: it allows {max(available, 0)} more "
            f"'{event}' event(s) and this call needs {count}. Raise the run's maximum "
            "charge to continue."
        )


@asynccontextmanager
async def metered(event: str, count: int = 1) -> AsyncIterator[None]:
    """Reserve ``count`` events, run the body, then charge them only if it succeeded."""
    async with _lock:
        await ensure_can_charge(event, count)
        _reserved[event] += count
    try:
        yield
        try:
            await charge(event, count)
        except Exception as err:
            # The work is done and the run has paid its compute: losing one
            # event's revenue is better than throwing the result away.
            log_extra("Charging failed; result returned", event=event, error=str(err))
    finally:
        # Synchronous, so a cancellation cannot interrupt it and leave the
        # reservation behind. Until it runs, a finished charge is counted both
        # by the meter and here, which errs towards refusing, never overspending.
        _release(event, count)


def _release(event: str, count: int) -> None:
    _reserved[event] -= count
    if _reserved[event] <= 0:
        del _reserved[event]


async def charge(event: str, count: int = 1) -> None:
    """Charge ``count`` occurrences of ``event`` (no-op unless a meter is installed)."""
    if count > 0:
        await _meter.charge(event, count)
