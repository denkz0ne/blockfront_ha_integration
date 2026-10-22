"""Shared per-credential request pacing for BlockFront API calls."""

from __future__ import annotations

import asyncio
import heapq
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from itertools import count
from time import monotonic


class RequestScheduler:
    """Serialize requests per API scope and share upstream cooldowns."""

    def __init__(self, *, minimum_spacing: float = 0.25) -> None:
        self._minimum_spacing = minimum_spacing
        self._conditions: dict[str, asyncio.Condition] = {}
        self._queues: dict[str, list[tuple[int, int, asyncio.Future[None]]]] = {}
        self._active: set[str] = set()
        self._next_allowed: dict[str, float] = {}
        self._paused_until: dict[str, float] = {}
        self._failures: dict[str, int] = {}
        self._sequence = count()

    @asynccontextmanager
    async def request(self, scope: str, *, priority: int = 0) -> AsyncIterator[None]:
        """Acquire a priority slot, respecting pacing and shared Retry-After."""
        key = f"{id(asyncio.get_running_loop())}:{scope}"
        condition = self._conditions.setdefault(key, asyncio.Condition())
        queue = self._queues.setdefault(key, [])
        waiter = asyncio.get_running_loop().create_future()
        item = (-priority, next(self._sequence), waiter)
        async with condition:
            heapq.heappush(queue, item)
            try:
                while key in self._active or queue[0][2] is not waiter:
                    await condition.wait()
                heapq.heappop(queue)
                self._active.add(key)
            except asyncio.CancelledError:
                queue.remove(item)
                heapq.heapify(queue)
                condition.notify_all()
                raise
        try:
            now = monotonic()
            wait_for = max(self._next_allowed.get(key, 0), self._paused_until.get(key, 0)) - now
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            self._next_allowed[key] = monotonic() + self._minimum_spacing
            yield
        finally:
            async with condition:
                self._active.discard(key)
                condition.notify_all()

    def pause(self, scope: str, seconds: float) -> None:
        """Pause all clients sharing scope after a quota response."""
        key = f"{id(asyncio.get_running_loop())}:{scope}"
        self._paused_until[key] = max(self._paused_until.get(key, 0), monotonic() + max(0, seconds))

    def transient_failure(self, scope: str) -> None:
        """Apply bounded exponential backoff after a transient transport error."""
        key = f"{id(asyncio.get_running_loop())}:{scope}"
        failures = min(self._failures.get(key, 0) + 1, 8)
        self._failures[key] = failures
        self.pause(scope, min(2 ** (failures - 1), 60))

    def successful(self, scope: str) -> None:
        """Reset transient backoff after a successful exchange."""
        key = f"{id(asyncio.get_running_loop())}:{scope}"
        self._failures.pop(key, None)
