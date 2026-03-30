# Copyright 2026 Protocol Wealth LLC
# Licensed under the MIT License
# https://github.com/Protocol-Wealth/pw-router

"""In-memory sliding window rate limiter. Resets on restart."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import MutableSequence


class RateLimiter:
    """Per-key sliding window rate limiter.

    Args:
        max_requests: Maximum requests per window.
        window_seconds: Window duration in seconds.
    """

    def __init__(self, max_requests: int = 60, window_seconds: float = 60.0) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: dict[str, MutableSequence[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> bool:
        """Check if a request from `key` is within the rate limit.

        Returns True if allowed, False if rate-limited.
        """
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            timestamps = self._timestamps[key]
            # Prune expired entries
            while timestamps and timestamps[0] < cutoff:
                timestamps.pop(0)

            if len(timestamps) >= self.max_requests:
                return False

            timestamps.append(now)
            return True

    def remaining(self, key: str) -> int:
        """Return how many requests remain in the current window."""
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            timestamps = self._timestamps[key]
            while timestamps and timestamps[0] < cutoff:
                timestamps.pop(0)
            return max(0, self.max_requests - len(timestamps))
