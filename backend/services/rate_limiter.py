from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import RLock
import uuid

from config.settings import settings


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


class RedisSlidingWindowRateLimiter:
    """Atomic Redis sorted-set limiter shared by every API replica."""

    _SCRIPT = """
    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local cutoff = tonumber(ARGV[2])
    local limit = tonumber(ARGV[3])
    local member = ARGV[4]
    local ttl = tonumber(ARGV[5])
    redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)
    local count = redis.call('ZCARD', key)
    if count >= limit then
      local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
      return {0, 0, oldest[2] or now}
    end
    redis.call('ZADD', key, now, member)
    redis.call('EXPIRE', key, ttl)
    return {1, limit - count - 1, 0}
    """

    def __init__(self, limit: int, window_seconds: int, namespace: str) -> None:
        import redis

        self.limit = limit
        self.window_seconds = window_seconds
        self.namespace = namespace
        self.client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        self.client.ping()
        self.script = self.client.register_script(self._SCRIPT)

    def check(self, key: str, now: float | None = None) -> RateLimitDecision:
        current = time.time() if now is None else now
        redis_key = f"nova:rate:{self.namespace}:{key}"
        allowed, remaining, oldest = self.script(
            keys=[redis_key],
            args=[current, current - self.window_seconds, self.limit, uuid.uuid4().hex, self.window_seconds + 1],
        )
        retry_after = 0 if allowed else max(1, int(float(oldest) + self.window_seconds - current) + 1)
        return RateLimitDecision(bool(allowed), self.limit, int(remaining), retry_after)

    def clear(self) -> None:
        for key in self.client.scan_iter(match=f"nova:rate:{self.namespace}:*"):
            self.client.delete(key)


def create_rate_limiter(limit: int, window_seconds: int, namespace: str):
    if settings.REDIS_URL:
        return RedisSlidingWindowRateLimiter(limit, window_seconds, namespace)
    return SlidingWindowRateLimiter(limit, window_seconds)
