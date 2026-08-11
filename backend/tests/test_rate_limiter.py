import pytest

from services.rate_limiter import SlidingWindowRateLimiter


def test_sliding_window_blocks_and_recovers() -> None:
    limiter = SlidingWindowRateLimiter(limit=2, window_seconds=10)

    assert limiter.check("user", now=0).allowed is True
    second = limiter.check("user", now=1)
    assert second.allowed is True
    assert second.remaining == 0

    blocked = limiter.check("user", now=2)
    assert blocked.allowed is False
    assert blocked.retry_after == 9

    recovered = limiter.check("user", now=11)
    assert recovered.allowed is True
    assert recovered.remaining == 1


def test_rate_limit_keys_are_isolated() -> None:
    limiter = SlidingWindowRateLimiter(limit=1, window_seconds=30)

    assert limiter.check("user-a", now=5).allowed is True
    assert limiter.check("user-a", now=6).allowed is False
    assert limiter.check("user-b", now=6).allowed is True


def test_rate_limiter_validates_configuration() -> None:
    with pytest.raises(ValueError):
        SlidingWindowRateLimiter(limit=0, window_seconds=10)
    with pytest.raises(ValueError):
        SlidingWindowRateLimiter(limit=10, window_seconds=0)
