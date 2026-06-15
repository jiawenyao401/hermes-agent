"""Login rate limiter — sliding window per IP."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict


class RateLimiter:
    """In-process sliding-window rate limiter for login attempts."""

    def __init__(self, max_attempts: int = 5, window_seconds: float = 60.0):
        self._max = max_attempts
        self._window = window_seconds
        self._attempts: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def is_limited(self, key: str) -> bool:
        """True if ``key`` has exceeded the attempt budget."""
        now = time.monotonic()
        cutoff = now - self._window
        bucket_key = key or "_unknown_"
        with self._lock:
            bucket = self._attempts[bucket_key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self._max:
                return True
            bucket.append(now)
            return False

    def reset(self) -> None:
        """Clear all rate-limit buckets (for testing)."""
        with self._lock:
            self._attempts.clear()
