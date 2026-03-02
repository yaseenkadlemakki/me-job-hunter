"""Per-site async rate limiter with jitter."""

from __future__ import annotations

import asyncio
import random
import time
from collections import defaultdict
from src.utils.logger import setup_logger

logger = setup_logger("rate_limiter")


class RateLimiter:
    """Async rate limiter with per-site delay and jitter."""

    def __init__(self, default_delay: float = 2.0, jitter: float = 0.5):
        self.default_delay = default_delay
        self.jitter = jitter
        self._last_request: dict[str, float] = defaultdict(float)
        self._delays: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def set_delay(self, site: str, delay: float) -> None:
        """Configure delay for a specific site."""
        self._delays[site] = delay

    def get_delay(self, site: str) -> float:
        return self._delays.get(site, self.default_delay)

    async def wait(self, site: str) -> None:
        """Wait the appropriate amount before making a request to site."""
        async with self._locks[site]:
            delay = self.get_delay(site)
            jitter = random.uniform(0, self.jitter)
            total_delay = delay + jitter

            elapsed = time.monotonic() - self._last_request[site]
            remaining = total_delay - elapsed
            if remaining > 0:
                logger.debug(f"Rate limiting {site}: sleeping {remaining:.2f}s")
                await asyncio.sleep(remaining)

            self._last_request[site] = time.monotonic()


# Global rate limiter instance
_rate_limiter: RateLimiter | None = None


def get_rate_limiter(config: dict | None = None) -> RateLimiter:
    """Get or create the global rate limiter, optionally configured from config."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
        if config:
            rate_limits = config.get("rate_limits", {})
            for site, delay in rate_limits.items():
                _rate_limiter.set_delay(site, float(delay))
    return _rate_limiter
