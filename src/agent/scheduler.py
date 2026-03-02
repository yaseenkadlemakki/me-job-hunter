"""APScheduler setup for periodic job search runs."""

from __future__ import annotations

import asyncio
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.utils.logger import setup_logger

logger = setup_logger("scheduler")


class JobHunterScheduler:
    """Periodic scheduler that runs the agent on a configurable interval."""

    def __init__(self, orchestrator, config: dict = None):
        self.orchestrator = orchestrator
        self.config = config or {}
        scheduler_cfg = config.get("scheduler", {}) if config else {}
        self.interval_hours = scheduler_cfg.get("interval_hours", 6)
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self._running = False

    def start(self) -> None:
        """Start the scheduler — blocks on the event loop."""
        self.scheduler.add_job(
            func=self._run_job,
            trigger=IntervalTrigger(hours=self.interval_hours),
            id="job_hunt",
            name="Job Hunter Run",
            replace_existing=True,
            next_run_time=datetime.utcnow(),  # run immediately on start
        )
        self.scheduler.start()
        logger.info(
            f"Scheduler started — running every {self.interval_hours}h. "
            f"First run: now"
        )

        try:
            asyncio.get_event_loop().run_forever()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler stopping...")
            self.scheduler.shutdown()

    async def _run_job(self) -> None:
        """Run the orchestrator (called by scheduler)."""
        logger.info(f"Scheduler triggered run at {datetime.utcnow().isoformat()}")
        try:
            stats = await self.orchestrator.run()
            logger.info(
                f"Scheduled run complete: {stats['total_new']} new jobs, "
                f"{stats['total_notified']} notifications sent"
            )
        except Exception as e:
            logger.error(f"Scheduled run failed: {e}", exc_info=True)

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler stopped")
