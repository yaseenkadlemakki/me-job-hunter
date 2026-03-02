"""Main agent orchestrator — the core run loop."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Optional

from src.connectors.linkedin import LinkedInConnector
from src.connectors.indeed import IndeedConnector
from src.connectors.bayt import BaytConnector
from src.connectors.gulftarget import GulfTalentConnector
from src.connectors.naukrigulf import NaukriGulfConnector
from src.matching.scorer import Scorer
from src.matching.filters import JobFilter
from src.parsers.job_parser import JobParser
from src.parsers.resume_parser import load_candidate_profile
from src.storage.database import Database
from src.storage.vector_store import VectorStore
from src.notifications.email_service import EmailService
from src.utils.logger import setup_logger

logger = setup_logger("orchestrator")


class JobHunterOrchestrator:
    """Orchestrates the full job search pipeline."""

    def __init__(self, config: dict, dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run

        # Load candidate profile
        self.candidate_profile = load_candidate_profile(config=config)
        logger.info(f"Loaded candidate profile: {self.candidate_profile['name']}")

        # Initialize components
        self.db = Database(url=config.get("database", {}).get("url"))
        self.db.init_db()

        self.vector_store = VectorStore(
            persist_directory=config.get("vector_store", {}).get("persist_directory", "./data/chroma"),
            collection_name=config.get("vector_store", {}).get("collection_name", "job_postings"),
        )

        self.scorer = Scorer(config=config)
        self.job_filter = JobFilter(config=config)
        self.job_parser = JobParser()
        self.email_service = EmailService(config=config)

        # Initialize connectors
        self.connectors = [
            LinkedInConnector(config=config),
            IndeedConnector(config=config),
            BaytConnector(config=config),
            GulfTalentConnector(config=config),
            NaukriGulfConnector(config=config),
        ]

        self.min_score = config.get("filters", {}).get("min_relevance_score", 80)
        self.max_jobs_per_run = config.get("scheduler", {}).get("max_jobs_per_run", 50)

    async def run(self) -> dict:
        """Execute a full scrape + score + notify cycle."""
        run_start = time.monotonic()
        run_stats = {
            "started_at": datetime.utcnow().isoformat(),
            "connectors": {},
            "total_scraped": 0,
            "total_new": 0,
            "total_passed_filter": 0,
            "total_scored": 0,
            "total_notified": 0,
            "errors": [],
        }

        logger.info("=" * 60)
        logger.info(f"Job Hunter run starting — {run_stats['started_at']}")
        logger.info(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        logger.info("=" * 60)

        total_jobs_processed = 0

        for connector in self.connectors:
            if total_jobs_processed >= self.max_jobs_per_run:
                logger.info(f"Max jobs per run ({self.max_jobs_per_run}) reached, stopping")
                break

            connector_stats = {
                "scraped": 0,
                "new": 0,
                "passed_filter": 0,
                "scored": 0,
                "notified": 0,
                "errors": [],
            }
            connector_start = time.monotonic()

            logger.info(f"--- Running connector: {connector.name} ---")

            try:
                raw_jobs = await connector._safe_scrape()
                connector_stats["scraped"] = len(raw_jobs)
                run_stats["total_scraped"] += len(raw_jobs)
                logger.info(f"[{connector.name}] Scraped {len(raw_jobs)} jobs")

                for raw_job in raw_jobs:
                    if total_jobs_processed >= self.max_jobs_per_run:
                        break

                    try:
                        result = await self._process_job(raw_job, connector.name, connector_stats)
                        if result:
                            total_jobs_processed += 1
                    except Exception as e:
                        err_msg = f"Job processing error: {e}"
                        logger.error(err_msg, exc_info=True)
                        connector_stats["errors"].append(err_msg)

            except Exception as e:
                err_msg = f"Connector {connector.name} failed: {e}"
                logger.error(err_msg, exc_info=True)
                connector_stats["errors"].append(err_msg)
                run_stats["errors"].append(err_msg)

            # Update aggregate stats
            run_stats["total_new"] += connector_stats["new"]
            run_stats["total_passed_filter"] += connector_stats["passed_filter"]
            run_stats["total_scored"] += connector_stats["scored"]
            run_stats["total_notified"] += connector_stats["notified"]
            run_stats["connectors"][connector.name] = connector_stats

            # Save scraping log
            duration = time.monotonic() - connector_start
            self.db.save_scraping_log({
                "source": connector.name,
                "jobs_found": connector_stats["scraped"],
                "jobs_new": connector_stats["new"],
                "jobs_scored": connector_stats["scored"],
                "jobs_notified": connector_stats["notified"],
                "errors": "; ".join(connector_stats["errors"]) if connector_stats["errors"] else None,
                "duration_seconds": round(duration, 2),
            })

            logger.info(
                f"[{connector.name}] Done: {connector_stats['scraped']} scraped, "
                f"{connector_stats['new']} new, "
                f"{connector_stats['scored']} scored, "
                f"{connector_stats['notified']} notified"
            )

        run_stats["duration_seconds"] = round(time.monotonic() - run_start, 2)
        run_stats["completed_at"] = datetime.utcnow().isoformat()

        self._log_run_summary(run_stats)
        return run_stats

    async def _process_job(self, raw_job: dict, source: str, stats: dict) -> bool:
        """Process a single job through the full pipeline. Returns True if processed."""
        raw_job["source"] = source

        # Parse and normalize
        job = self.job_parser.parse(raw_job)

        if not job.get("url") or not job.get("title"):
            logger.debug(f"Skipping job without URL or title")
            return False

        # Deduplication check
        if self.db.job_exists(job["url"]):
            logger.debug(f"Duplicate job: {job['url']}")
            return False

        # Pre-filter (fast, no LLM)
        passes, reason = self.job_filter.passes(job)
        if not passes:
            logger.debug(f"Filtered out '{job['title']}': {reason}")
            return False

        stats["passed_filter"] += 1

        # Save to DB
        if not self.dry_run:
            saved_job = self.db.save_job(job)
            if saved_job is None:
                return False  # Duplicate, race condition
            job_id = saved_job.id
        else:
            job_id = -1
            logger.info(f"[DRY RUN] Would save: '{job['title']}' @ '{job['company']}'")

        stats["new"] += 1

        # Add to vector store
        if not self.dry_run:
            self.vector_store.add_job(job)

        # Score with Claude
        try:
            score = await self.scorer.score(job, self.candidate_profile)
            stats["scored"] += 1

            if not self.dry_run and job_id > 0:
                self.db.save_score(job_id, score)

            final_score = score.get("final_score", 0)
            logger.info(
                f"Job scored: [{final_score:.0f}/100] '{job['title']}' @ '{job['company']}' ({job['location']})"
            )

            # Notify if score is high enough
            if final_score >= self.min_score:
                if self.dry_run:
                    logger.info(f"[DRY RUN] Would send email for score {final_score:.0f}")
                else:
                    # Estimate salary if not present
                    if not job.get("salary_estimated_aed") and not job.get("salary_raw"):
                        try:
                            est = await self.scorer.estimate_salary_aed(job)
                            if est:
                                job["salary_estimated_aed"] = est
                        except Exception:
                            pass

                    success = self.email_service.send_job_alert(job, score)
                    if success:
                        stats["notified"] += 1
                        self.db.save_notification(
                            job_id=job_id,
                            email_to=self.email_service.to_email,
                            success=True,
                        )
                    else:
                        self.db.save_notification(
                            job_id=job_id,
                            email_to=self.email_service.to_email,
                            success=False,
                            error="Email send failed",
                        )

        except Exception as e:
            logger.error(f"Scoring failed for '{job['title']}': {e}")
            stats.setdefault("errors", []).append(f"Scoring: {e}")

        return True

    def _log_run_summary(self, stats: dict) -> None:
        logger.info("=" * 60)
        logger.info("RUN COMPLETE")
        logger.info(f"  Duration:   {stats.get('duration_seconds', 0):.1f}s")
        logger.info(f"  Scraped:    {stats['total_scraped']}")
        logger.info(f"  New:        {stats['total_new']}")
        logger.info(f"  Filtered:   {stats['total_passed_filter']}")
        logger.info(f"  Scored:     {stats['total_scored']}")
        logger.info(f"  Notified:   {stats['total_notified']}")
        if stats["errors"]:
            logger.warning(f"  Errors:     {len(stats['errors'])}")
        logger.info("=" * 60)

    def get_status(self) -> dict:
        """Get current database statistics."""
        return self.db.get_stats()

    def get_top_jobs(self, limit: int = 20, min_score: float = 80.0) -> list[dict]:
        """Get top-scored jobs from the database."""
        return self.db.get_top_jobs(limit=limit, min_score=min_score)
