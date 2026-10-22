"""Request scheduler behavior tests."""

from __future__ import annotations

import asyncio
from time import monotonic

import pytest

from custom_components.blockfront.request_scheduler import RequestScheduler


@pytest.mark.asyncio
async def test_scheduler_serializes_requests_in_the_same_scope() -> None:
    scheduler = RequestScheduler(minimum_spacing=0)
    active = 0
    peak = 0

    async def request() -> None:
        nonlocal active, peak
        async with scheduler.request("same"):
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1

    await asyncio.gather(*(request() for _ in range(8)))
    assert peak == 1


@pytest.mark.asyncio
async def test_rate_limit_pause_is_shared_only_with_matching_scope() -> None:
    scheduler = RequestScheduler(minimum_spacing=0)
    scheduler.pause("origin-and-key-a", 0.05)

    start = monotonic()
    async with scheduler.request("origin-and-key-a"):
        shared_wait = monotonic() - start

    start = monotonic()
    async with scheduler.request("origin-and-key-b"):
        isolated_wait = monotonic() - start

    assert shared_wait >= 0.04
    assert isolated_wait < 0.03


@pytest.mark.asyncio
async def test_waiting_requests_are_released_by_priority() -> None:
    scheduler = RequestScheduler(minimum_spacing=0)
    order: list[str] = []

    async def request(name: str, priority: int) -> None:
        async with scheduler.request("priority", priority=priority):
            order.append(name)

    async with scheduler.request("priority", priority=0):
        low = asyncio.create_task(request("low", 1))
        await asyncio.sleep(0.01)
        high = asyncio.create_task(request("high", 10))
        await asyncio.sleep(0.01)
    await asyncio.gather(low, high)
    assert order == ["high", "low"]
