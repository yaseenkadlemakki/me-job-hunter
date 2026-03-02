"""Functional tests for the JobHunterOrchestrator."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.orchestrator import JobHunterOrchestrator


@pytest.fixture
def mock_connectors():
    """Create 5 mock connectors that return empty lists by default."""
    connectors = []
    names = ["linkedin", "indeed", "bayt", "gulftarget", "naukrigulf"]
    for name in names:
        c = MagicMock()
        c.name = name
        c._safe_scrape = AsyncMock(return_value=[])
        connectors.append(c)
    return connectors


def make_raw_job(n, source="linkedin", title="Director of Engineering",
                  location="Dubai, UAE", url=None):
    url = url or f"https://{source}.com/jobs/view/{n}"
    return {
        "source": source,
        "title": title,
        "company": "Gulf Tech Corp",
        "location": location,
        "url": url,
        "description": "Director of Engineering role in Dubai. Kubernetes, AWS, DevOps required.",
        "salary_raw": "AED 1,200,000 - 1,500,000",
        "posted_date": "2 days ago",
    }


def make_high_score_response():
    return {
        "skill_overlap": 90,
        "seniority_alignment": 95,
        "industry_alignment": 80,
        "compensation_confidence": 85,
        "location_relevance": 100,
        "explanation": "Strong match.",
        "positioning_strategy": "Emphasize scale.",
        "final_score": 90.25,
    }


def make_low_score_response():
    return {
        "skill_overlap": 40,
        "seniority_alignment": 30,
        "industry_alignment": 40,
        "compensation_confidence": 30,
        "location_relevance": 20,
        "explanation": "Poor match.",
        "positioning_strategy": "Skip.",
        "final_score": 34.25,
    }


@pytest.fixture
def orchestrator(config):
    """Build an orchestrator with all dependencies mocked."""
    with patch("src.agent.orchestrator.LinkedInConnector") as MockLI, \
         patch("src.agent.orchestrator.IndeedConnector") as MockII, \
         patch("src.agent.orchestrator.BaytConnector") as MockBayt, \
         patch("src.agent.orchestrator.GulfTalentConnector") as MockGT, \
         patch("src.agent.orchestrator.NaukriGulfConnector") as MockNG, \
         patch("src.agent.orchestrator.Scorer") as MockScorer, \
         patch("src.agent.orchestrator.JobFilter") as MockFilter, \
         patch("src.agent.orchestrator.JobParser") as MockParser, \
         patch("src.agent.orchestrator.Database") as MockDB, \
         patch("src.agent.orchestrator.VectorStore") as MockVS, \
         patch("src.agent.orchestrator.EmailService") as MockEmail, \
         patch("src.agent.orchestrator.load_candidate_profile") as MockProfile:

        # Profile
        MockProfile.return_value = {
            "name": "Yaseen Kadlemakki",
            "email": "test@test.com",
            "skills": ["Kubernetes", "AWS"],
            "industries": ["Cloud"],
            "target_comp_aed": 1200000,
        }

        # DB
        mock_db = MagicMock()
        mock_db.job_exists.return_value = False
        mock_db.save_job.return_value = MagicMock(id=1)
        mock_db.save_score = MagicMock()
        mock_db.save_notification = MagicMock()
        mock_db.save_scraping_log = MagicMock()
        MockDB.return_value = mock_db

        # Vector store
        mock_vs = MagicMock()
        mock_vs.add_job = MagicMock()
        MockVS.return_value = mock_vs

        # Scorer
        mock_scorer = MagicMock()
        mock_scorer.score = AsyncMock(return_value=make_high_score_response())
        mock_scorer.passes_filter.return_value = True
        mock_scorer.estimate_salary_aed = AsyncMock(return_value=None)
        MockScorer.return_value = mock_scorer

        # Filter
        mock_filter = MagicMock()
        mock_filter.passes.return_value = (True, "ok")
        MockFilter.return_value = mock_filter

        # Parser
        mock_parser = MagicMock()
        mock_parser.parse.side_effect = lambda raw: {
            **raw,
            "seniority_level": "director",
            "salary_estimated_aed": 1300000.0,
        }
        MockParser.return_value = mock_parser

        # Email
        mock_email = MagicMock()
        mock_email.send_job_alert.return_value = True
        mock_email.to_email = "test@test.com"
        MockEmail.return_value = mock_email

        # Connectors
        connectors = []
        for MockConn, name in zip(
            [MockLI, MockII, MockBayt, MockGT, MockNG],
            ["linkedin", "indeed", "bayt", "gulftarget", "naukrigulf"]
        ):
            mock_conn = MagicMock()
            mock_conn.name = name
            mock_conn._safe_scrape = AsyncMock(return_value=[])
            MockConn.return_value = mock_conn
            connectors.append(mock_conn)

        orch = JobHunterOrchestrator(config=config)

        # Inject mock connectors
        orch.connectors = connectors
        orch.db = mock_db
        orch.vector_store = mock_vs
        orch.scorer = mock_scorer
        orch.job_filter = mock_filter
        orch.job_parser = mock_parser
        orch.email_service = mock_email

        yield orch, connectors, mock_db, mock_scorer, mock_filter, mock_email, mock_vs


class TestOrchestratorRun:
    """Test the main run() loop."""

    @pytest.mark.asyncio
    async def test_empty_run_returns_stats(self, orchestrator):
        orch, connectors, *_ = orchestrator
        stats = await orch.run()
        assert isinstance(stats, dict)
        assert "total_scraped" in stats

    @pytest.mark.asyncio
    async def test_empty_run_total_scraped_is_zero(self, orchestrator):
        orch, connectors, *_ = orchestrator
        stats = await orch.run()
        assert stats["total_scraped"] == 0

    @pytest.mark.asyncio
    async def test_scraping_logs_saved_for_all_connectors(self, orchestrator):
        orch, connectors, mock_db, *_ = orchestrator
        await orch.run()
        assert mock_db.save_scraping_log.call_count == 5

    @pytest.mark.asyncio
    async def test_3_jobs_pass_filter_1_email_sent(self, orchestrator):
        orch, connectors, mock_db, mock_scorer, mock_filter, mock_email, mock_vs = orchestrator

        # First connector returns 3 jobs
        jobs = [make_raw_job(i) for i in range(3)]
        connectors[0]._safe_scrape = AsyncMock(return_value=jobs)

        # All pass filter, all score >= 80
        mock_filter.passes.return_value = (True, "ok")
        mock_scorer.score = AsyncMock(return_value=make_high_score_response())
        mock_email.send_job_alert.return_value = True

        stats = await orch.run()
        assert stats["total_notified"] == 3
        assert mock_email.send_job_alert.call_count == 3

    @pytest.mark.asyncio
    async def test_duplicate_jobs_skipped(self, orchestrator):
        orch, connectors, mock_db, mock_scorer, *_ = orchestrator

        jobs = [make_raw_job(1)]
        connectors[0]._safe_scrape = AsyncMock(return_value=jobs)

        # All duplicates
        mock_db.job_exists.return_value = True

        stats = await orch.run()
        # Scorer should NOT be called for duplicates
        mock_scorer.score.assert_not_called()
        assert stats["total_new"] == 0

    @pytest.mark.asyncio
    async def test_connector_failure_others_continue(self, orchestrator):
        orch, connectors, mock_db, *_ = orchestrator

        # First connector raises exception
        connectors[0]._safe_scrape = AsyncMock(side_effect=Exception("Scraper failed"))
        # Second connector returns jobs
        connectors[1]._safe_scrape = AsyncMock(return_value=[make_raw_job(1, source="indeed")])

        stats = await orch.run()
        assert len(stats["errors"]) >= 1
        # Total scraped from connector 2+
        assert stats["total_scraped"] >= 1

    @pytest.mark.asyncio
    async def test_low_score_no_email_sent(self, orchestrator):
        orch, connectors, mock_db, mock_scorer, mock_filter, mock_email, mock_vs = orchestrator

        jobs = [make_raw_job(1)]
        connectors[0]._safe_scrape = AsyncMock(return_value=jobs)
        mock_filter.passes.return_value = (True, "ok")
        mock_scorer.score = AsyncMock(return_value=make_low_score_response())

        stats = await orch.run()
        assert stats["total_notified"] == 0
        mock_email.send_job_alert.assert_not_called()

    @pytest.mark.asyncio
    async def test_filter_rejects_job_not_scored(self, orchestrator):
        orch, connectors, mock_db, mock_scorer, mock_filter, *_ = orchestrator

        jobs = [make_raw_job(1, title="Senior Software Engineer", location="London")]
        connectors[0]._safe_scrape = AsyncMock(return_value=jobs)
        mock_filter.passes.return_value = (False, "not a senior role: senior software engineer")

        stats = await orch.run()
        mock_scorer.score.assert_not_called()
        assert stats["total_passed_filter"] == 0

    @pytest.mark.asyncio
    async def test_max_jobs_per_run_respected(self, orchestrator, config):
        orch, connectors, *_ = orchestrator
        orch.max_jobs_per_run = 2

        # First connector returns 5 jobs
        jobs = [make_raw_job(i) for i in range(5)]
        connectors[0]._safe_scrape = AsyncMock(return_value=jobs)

        stats = await orch.run()
        # Should not process more than max_jobs_per_run
        assert stats["total_new"] <= 2

    @pytest.mark.asyncio
    async def test_stats_include_connector_breakdown(self, orchestrator):
        orch, connectors, *_ = orchestrator
        stats = await orch.run()
        assert "connectors" in stats
        assert len(stats["connectors"]) == 5

    @pytest.mark.asyncio
    async def test_job_without_url_skipped(self, orchestrator):
        orch, connectors, mock_db, mock_scorer, *_ = orchestrator

        jobs = [{"title": "Director", "company": "C", "location": "Dubai", "url": "", "source": "linkedin", "description": ""}]
        connectors[0]._safe_scrape = AsyncMock(return_value=jobs)

        stats = await orch.run()
        mock_scorer.score.assert_not_called()

    @pytest.mark.asyncio
    async def test_job_without_title_skipped(self, orchestrator):
        orch, connectors, mock_db, mock_scorer, *_ = orchestrator

        orch.job_parser.parse.side_effect = lambda raw: {
            **raw,
            "title": "",  # empty title
            "seniority_level": "unknown",
        }
        jobs = [make_raw_job(1)]
        connectors[0]._safe_scrape = AsyncMock(return_value=jobs)

        stats = await orch.run()
        mock_scorer.score.assert_not_called()

    @pytest.mark.asyncio
    async def test_dry_run_does_not_save_to_db(self, config):
        """In dry_run mode, no DB saves should occur."""
        with patch("src.agent.orchestrator.LinkedInConnector"), \
             patch("src.agent.orchestrator.IndeedConnector"), \
             patch("src.agent.orchestrator.BaytConnector"), \
             patch("src.agent.orchestrator.GulfTalentConnector"), \
             patch("src.agent.orchestrator.NaukriGulfConnector"), \
             patch("src.agent.orchestrator.Scorer") as MockScorer, \
             patch("src.agent.orchestrator.JobFilter") as MockFilter, \
             patch("src.agent.orchestrator.JobParser") as MockParser, \
             patch("src.agent.orchestrator.Database") as MockDB, \
             patch("src.agent.orchestrator.VectorStore"), \
             patch("src.agent.orchestrator.EmailService"), \
             patch("src.agent.orchestrator.load_candidate_profile") as MockProfile:

            MockProfile.return_value = {"name": "T", "skills": [], "industries": [], "target_comp_aed": 1200000}
            mock_db = MagicMock()
            mock_db.job_exists.return_value = False
            mock_db.save_scraping_log = MagicMock()
            MockDB.return_value = mock_db

            mock_filter = MagicMock()
            mock_filter.passes.return_value = (True, "ok")
            MockFilter.return_value = mock_filter

            mock_parser = MagicMock()
            mock_parser.parse.side_effect = lambda raw: {**raw, "seniority_level": "director"}
            MockParser.return_value = mock_parser

            mock_scorer = MagicMock()
            mock_scorer.score = AsyncMock(return_value=make_high_score_response())
            MockScorer.return_value = mock_scorer

            orch = JobHunterOrchestrator(config=config, dry_run=True)

            mock_conn = MagicMock()
            mock_conn.name = "linkedin"
            mock_conn._safe_scrape = AsyncMock(return_value=[make_raw_job(1)])
            orch.connectors = [mock_conn]

            await orch.run()
            mock_db.save_job.assert_not_called()
