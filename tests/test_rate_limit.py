# Copyright 2026 Protocol Wealth LLC
# Licensed under the MIT License
# https://github.com/Protocol-Wealth/pw-router

"""Tests for rate limiter."""

from pw_router.rate_limit import RateLimiter


class TestRateLimiter:
    def test_allows_under_limit(self):
        rl = RateLimiter(max_requests=5, window_seconds=60)
        for _ in range(5):
            assert rl.is_allowed("client-1") is True

    def test_blocks_over_limit(self):
        rl = RateLimiter(max_requests=3, window_seconds=60)
        assert rl.is_allowed("client-1") is True
        assert rl.is_allowed("client-1") is True
        assert rl.is_allowed("client-1") is True
        assert rl.is_allowed("client-1") is False

    def test_separate_keys(self):
        rl = RateLimiter(max_requests=2, window_seconds=60)
        assert rl.is_allowed("a") is True
        assert rl.is_allowed("a") is True
        assert rl.is_allowed("a") is False
        # Different key should still be allowed
        assert rl.is_allowed("b") is True

    def test_remaining(self):
        rl = RateLimiter(max_requests=5, window_seconds=60)
        assert rl.remaining("client-1") == 5
        rl.is_allowed("client-1")
        assert rl.remaining("client-1") == 4
        rl.is_allowed("client-1")
        rl.is_allowed("client-1")
        assert rl.remaining("client-1") == 2

    def test_window_expiry(self):
        """Requests expire after the window."""
        rl = RateLimiter(max_requests=2, window_seconds=0.01)
        assert rl.is_allowed("client-1") is True
        assert rl.is_allowed("client-1") is True
        assert rl.is_allowed("client-1") is False

        import time

        time.sleep(0.02)  # Wait for window to expire

        assert rl.is_allowed("client-1") is True
