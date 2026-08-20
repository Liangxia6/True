"""Per-provider / credential concurrency and interval limiters."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class TokenBucket:
    rate_per_second: float
    capacity: float
    tokens: float = field(init=False)
    updated: float = field(init=False)

    def __post_init__(self) -> None:
        self.tokens = self.capacity
        self.updated = time.monotonic()

    async def acquire(self) -> None:
        while True:
            now = time.monotonic()
            elapsed = now - self.updated
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate_per_second)
            self.updated = now
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return
            wait = (1.0 - self.tokens) / max(self.rate_per_second, 1e-6)
            await asyncio.sleep(wait)


class CapacityPool:
    """Independent semaphores for submit / poll / collect / fetch / judge."""

    def __init__(
        self,
        *,
        submit: int = 2,
        poll: int = 4,
        collect: int = 2,
        fetch: int = 4,
        judge: int = 2,
    ) -> None:
        self.submit = asyncio.Semaphore(submit)
        self.poll = asyncio.Semaphore(poll)
        self.collect = asyncio.Semaphore(collect)
        self.fetch = asyncio.Semaphore(fetch)
        self.judge = asyncio.Semaphore(judge)
        self._provider_submit: dict[str, asyncio.Semaphore] = defaultdict(lambda: asyncio.Semaphore(submit))
        self._buckets: dict[str, TokenBucket] = {}

    def provider_submit(self, provider: str) -> asyncio.Semaphore:
        return self._provider_submit[provider]

    def bucket(self, key: str, *, rate_per_second: float = 1.0, capacity: float = 2.0) -> TokenBucket:
        if key not in self._buckets:
            self._buckets[key] = TokenBucket(rate_per_second=rate_per_second, capacity=capacity)
        return self._buckets[key]
