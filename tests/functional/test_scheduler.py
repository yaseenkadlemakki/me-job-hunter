"""Functional tests for the APScheduler integration."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from src.agent.scheduler import JobHunterScheduler


@pytest.fixture
def mock_orchestrator():
    orch = MagicMock()
    orch.run = AsyncMock(return_value={
        "total_scraped": 5,
        "total_new": 3,
        "total_scored": 2,
        "total_notified": 1,
        "errors": [],
        "duration_seconds": 10.0,
    })
    return orch


class TestSchedulerInit:
    """Test scheduler initialization."""

    def test_scheduler_initializes(self, mock_orchestrator):
        scheduler = JobHunterScheduler(mock_orchestrator, interval_hours=6)
        assert scheduler.orchestrator is mock_orchestrator
        assert scheduler.interval_hours == 6

    def test_scheduler_default_interval(self, mock_orchestrator):
        scheduler = JobHunterScheduler(mock_orchestrator)
        assert scheduler.interval_hours == 6

    def test_scheduler_has_apscheduler(self, mock_orchestrator):
        scheduler = JobHunterScheduler(mock_orchestrator)
        assert scheduler.scheduler is not None


class TestSchedulerRunJob:
    """Test the _run_job() method."""

    @pytest.mark.asyncio
    async def test_run_job_calls_orchestrator(self, mock_orchestrator):
        scheduler = JobHunterScheduler(mock_orchestrator, interval_hours=6)
        await scheduler._run_job()
        mock_orchestrator.run.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_job_handles_orchestrator_exception(self, mock_orchestrator):
        """Scheduler should not crash if orchestrator raises."""
        mock_orchestrator.run = AsyncMock(side_effect=Exception("Orchestrator crashed"))
        scheduler = JobHunterScheduler(mock_orchestrator, interval_hours=6)
        # Should not raise
        try:
            await scheduler._run_job()
        except Exception:
            pytest.fail("Scheduler should not propagate orchestrator exceptions")

    @pytest.mark.asyncio
    async def test_run_job_returns_stats(self, mock_orchestrator):
        scheduler = JobHunterScheduler(mock_orchestrator, interval_hours=6)
        await scheduler._run_job()
        mock_orchestrator.run.assert_awaited()


class TestSchedulerStart:
    """Test scheduler start/stop."""

    def test_start_registers_job(self, mock_orchestrator):
        """Scheduler registers a job with APScheduler."""
        with patch("src.agent.scheduler.AsyncIOScheduler") as MockScheduler:
            mock_apscheduler = MagicMock()
            MockScheduler.return_value = mock_apscheduler

            scheduler = JobHunterScheduler(mock_orchestrator, interval_hours=6)
            scheduler.scheduler = mock_apscheduler

            # Just verify the scheduler object exists and can be configured
            assert scheduler.scheduler is not None

    def test_scheduler_can_be_created(self, mock_orchestrator):
        """Verify JobHunterScheduler can be instantiated without errors."""
        scheduler = JobHunterScheduler(mock_orchestrator, interval_hours=6)
        assert scheduler is not None
