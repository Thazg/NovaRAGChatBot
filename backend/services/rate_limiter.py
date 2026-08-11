from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import RLock


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int


class SlidingWindowRateLimiter:
    """Thread-safe in-memory sliding-window limiter for a single API process."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        if limit <= 0 or window_seconds <= 0:
            raise ValueError("limit and window_seconds must be greater than zero")
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = RLock()

    def check(self, key: str, now: float | None = None) -> RateLimitDecision:
        current = time.monotonic() if now is None else now
        cutoff = current - self.window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()

            if len(events) >= self.limit:
                retry_after = max(1, int(events[0] + self.window_seconds - current) + 1)
                return RateLimitDecision(False, self.limit, 0, retry_after)

            events.append(current)
            remaining = max(0, self.limit - len(events))
            return RateLimitDecision(True, self.limit, remaining, 0)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
