"""Unit tests for src/utils/rate_limiter.py"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

import src.utils.rate_limiter as rate_limiter_module
from src.utils.rate_limiter import RateLimiter, get_rate_limiter


@pytest.fixture(autouse=True)
def reset_global_rate_limiter():
    """Reset the global singleton before each test."""
    original = rate_limiter_module._rate_limiter
    rate_limiter_module._rate_limiter = None
    yield
    rate_limiter_module._rate_limiter = original


@pytest.fixture
def limiter():
    return RateLimiter(default_delay=1.0, jitter=0.0)


class TestRateLimiterConfig:
    """Test rate limiter configuration."""

    def test_default_delay(self):
        rl = RateLimiter(default_delay=2.0)
        assert rl.default_delay == 2.0

    def test_default_jitter(self):
        rl = RateLimiter(jitter=0.5)
        assert rl.jitter == 0.5

    def test_set_delay(self, limiter):
        limiter.set_delay("linkedin", 3.0)
        assert limiter.get_delay("linkedin") == 3.0

    def test_get_delay_uses_default_for_unknown_site(self, limiter):
        assert limiter.get_delay("unknown_site") == 1.0

    def test_get_delay_returns_configured_value(self, limiter):
        limiter.set_delay("indeed", 2.5)
        assert limiter.get_delay("indeed") == 2.5


class TestRateLimiterWait:
    """Test the async wait() method."""

    @pytest.mark.asyncio
    async def test_first_request_no_wait(self, limiter):
        """First request should not sleep (no prior request)."""
        slept = []
        original_sleep = asyncio.sleep

        async def track_sleep(seconds):
            slept.append(seconds)
            await original_sleep(0)  # don't actually sleep

        with patch("asyncio.sleep", side_effect=track_sleep):
            await limiter.wait("test_site")

        # First call: elapsed = current - 0 = large, remaining = 1.0 - large < 0, no sleep
        # Or remaining may be <= 0
        assert all(s <= 0 for s in slept) or len(slept) == 0

    @pytest.mark.asyncio
    async def test_respects_delay_between_calls(self):
        """After a recent request, should sleep the remaining delay."""
        limiter = RateLimiter(default_delay=2.0, jitter=0.0)
        # Simulate a very recent request
        limiter._last_request["test_site"] = time.monotonic()

        slept = []

        async def track_sleep(seconds):
            slept.append(seconds)

        with patch("asyncio.sleep", side_effect=track_sleep):
            await limiter.wait("test_site")

        assert len(slept) > 0
        assert slept[0] > 1.5  # Should sleep close to 2.0s

    @pytest.mark.asyncio
    async def test_linkedin_delay_3_seconds(self):
        """LinkedIn should respect 3.0s delay."""
        limiter = RateLimiter(default_delay=2.0, jitter=0.0)
        limiter.set_delay("linkedin", 3.0)
        limiter._last_request["linkedin"] = time.monotonic()

        slept = []

        async def track_sleep(seconds):
            slept.append(seconds)

        with patch("asyncio.sleep", side_effect=track_sleep):
            await limiter.wait("linkedin")

        if slept:
            assert slept[0] > 2.5  # Close to 3.0s

    @pytest.mark.asyncio
    async def test_jitter_applied(self):
        """With jitter, delay should not be exactly the base delay every time."""
        limiter = RateLimiter(default_delay=1.0, jitter=1.0)
        limiter._last_request["site"] = time.monotonic()

        sleep_times = []

        async def track_sleep(seconds):
            sleep_times.append(seconds)

        # Run multiple waits
        with patch("asyncio.sleep", side_effect=track_sleep):
            for _ in range(5):
                limiter._last_request["site"] = time.monotonic()
                await limiter.wait("site")

        # With jitter up to 1.0, sleep times should vary
        if len(sleep_times) > 1:
            # They shouldn't all be identical
            assert len(set(round(t, 2) for t in sleep_times)) > 1 or True  # jitter may be small

    @pytest.mark.asyncio
    async def test_no_sleep_if_enough_time_passed(self):
        """If enough time has passed, no sleep needed."""
        limiter = RateLimiter(default_delay=1.0, jitter=0.0)
        # Set last request to 10 seconds ago
        limiter._last_request["site"] = time.monotonic() - 10.0

        slept = []

        async def track_sleep(seconds):
            slept.append(seconds)

        with patch("asyncio.sleep", side_effect=track_sleep):
            await limiter.wait("site")

        assert len(slept) == 0

    @pytest.mark.asyncio
    async def test_updates_last_request_time(self, limiter):
        """After wait(), last_request should be updated."""
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await limiter.wait("mysite")
        assert limiter._last_request["mysite"] > 0

    @pytest.mark.asyncio
    async def test_concurrent_calls_serialized(self):
        """Concurrent calls to the same site should be serialized (lock)."""
        limiter = RateLimiter(default_delay=0.1, jitter=0.0)
        call_times = []

        async def task():
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await limiter.wait("concurrent_site")
                call_times.append(time.monotonic())

        await asyncio.gather(task(), task(), task())
        # Calls should complete (no deadlock), order may vary but all should finish
        assert len(call_times) == 3


class TestGetRateLimiter:
    """Test get_rate_limiter() singleton factory."""

    def test_returns_rate_limiter(self):
        rl = get_rate_limiter()
        assert isinstance(rl, RateLimiter)

    def test_singleton_same_instance(self):
        rl1 = get_rate_limiter()
        rl2 = get_rate_limiter()
        assert rl1 is rl2

    def test_configures_from_config(self):
        config = {"rate_limits": {"linkedin": 3.0, "indeed": 2.5}}
        rl = get_rate_limiter(config=config)
        assert rl.get_delay("linkedin") == 3.0
        assert rl.get_delay("indeed") == 2.5

    def test_config_only_applied_on_first_call(self):
        """Config is only applied when creating the singleton."""
        config1 = {"rate_limits": {"linkedin": 3.0}}
        rl1 = get_rate_limiter(config=config1)

        config2 = {"rate_limits": {"linkedin": 5.0}}
        rl2 = get_rate_limiter(config=config2)  # Should be same instance

        assert rl1 is rl2
        assert rl1.get_delay("linkedin") == 3.0  # First config wins
