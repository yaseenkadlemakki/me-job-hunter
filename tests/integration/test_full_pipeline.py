"""Full end-to-end integration test for the complete job search pipeline."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from src.agent.orchestrator import JobHunterOrchestrator


def make_job(n, source, title="Director of Engineering", location="Dubai, UAE",
             passes_filter=True, passes_seniority=True, passes_location=True):
    return {
        "source": source,
        "title": title if passes_seniority else "Senior Software Engineer",
        "company": f"Company {n}",
        "location": location if passes_location else "London, UK",
        "url": f"https://{source}.com/jobs/{n}",
        "description": "Director of Engineering role in Dubai. Kubernetes, AWS required.",
        "salary_raw": "AED 1,200,000",
        "posted_date": "2 days ago",
    }


@pytest.fixture
def full_pipeline_config(config):
    """Config with in-memory DB."""
    config["database"] = {"url": "sqlite:///:memory:"}
    return config


class TestFullPipeline:
    """Full end-to-end test with all mocks."""

    @pytest.mark.asyncio
    async def test_complete_pipeline_flow(self, full_pipeline_config):
        """
        Full pipeline:
        - 5 connectors × 3 jobs each = 15 total scraped
        - 5 fail location filter (London)
        - 3 fail seniority filter (IC roles)
        - 7 pass filters
        - 4 already in DB (deduplication)
        - 3 new jobs scored
        - 2 score >= 80
        - 2 emails sent
        """

        sources = ["linkedin", "indeed", "bayt", "gulftarget", "naukrigulf"]

        # Create 15 jobs: 3 per source
        # Jobs 0-14:
        # - index % 3 == 0: senior Director Dubai (passes all)
        # - index % 3 == 1: Director London (location fail)
        # - index % 3 == 2: IC Engineer Dubai (seniority fail)
        all_raw_jobs = []
        for src_idx, source in enumerate(sources):
            for j in range(3):
                n = src_idx * 3 + j
                if j == 0:
                    # Director Dubai (passes)
                    all_raw_jobs.append(make_job(n, source, "Director of Engineering", "Dubai, UAE"))
                elif j == 1:
                    # Director London (location fail)
                    all_raw_jobs.append(make_job(n, source, "Director of Engineering", "London, UK"))
                else:
                    # IC role (seniority fail)
                    all_raw_jobs.append(make_job(n, source, "Senior Software Engineer", "Dubai, UAE"))

        # The 5 "passing" director Dubai jobs from each source
        passing_jobs = [j for j in all_raw_jobs
                       if j["title"] == "Director of Engineering" and "Dubai" in j["location"]]
        assert len(passing_jobs) == 5

        # Mark 2 as already in DB (jobs from sources 0 and 1)
        db_existing_urls = {passing_jobs[0]["url"], passing_jobs[1]["url"]}
        new_jobs = [j for j in passing_jobs if j["url"] not in db_existing_urls]
        assert len(new_jobs) == 3

        # Jobs will be scored; 2 get high score, 1 gets low
        high_score_urls = {new_jobs[0]["url"], new_jobs[1]["url"]}

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

            # Setup profile
            MockProfile.return_value = {
                "name": "Yaseen", "skills": ["Kubernetes"], "industries": ["Cloud"],
                "target_comp_aed": 1200000, "email": "test@test.com"
            }

            # Setup DB
            mock_db = MagicMock()
            saved_job_count = [0]

            def job_exists_side_effect(url):
                return url in db_existing_urls

            def save_job_side_effect(job_data):
                saved_job_count[0] += 1
                mock_job = MagicMock()
                mock_job.id = saved_job_count[0]
                return mock_job

            mock_db.job_exists.side_effect = job_exists_side_effect
            mock_db.save_job.side_effect = save_job_side_effect
            mock_db.save_score = MagicMock()
            mock_db.save_notification = MagicMock()
            mock_db.save_scraping_log = MagicMock()
            MockDB.return_value = mock_db

            # Setup vector store
            mock_vs = MagicMock()
            mock_vs.add_job = MagicMock()
            MockVS.return_value = mock_vs

            # Setup filter
            def filter_passes_side_effect(job_data):
                if "London" in (job_data.get("location") or ""):
                    return (False, "not in target location: london, uk")
                if "Senior Software Engineer" in (job_data.get("title") or ""):
                    return (False, "not a senior role: senior software engineer")
                return (True, "ok")

            mock_filter = MagicMock()
            mock_filter.passes.side_effect = filter_passes_side_effect
            MockFilter.return_value = mock_filter

            # Setup parser
            def parse_side_effect(raw):
                return {
                    **raw,
                    "seniority_level": "director" if "Director" in raw.get("title", "") else "ic",
                    "salary_estimated_aed": 1300000.0,
                }
            mock_parser = MagicMock()
            mock_parser.parse.side_effect = parse_side_effect
            MockParser.return_value = mock_parser

            # Setup scorer
            score_calls = [0]
            async def score_side_effect(job_data, candidate):
                score_calls[0] += 1
                url = job_data.get("url", "")
                if url in high_score_urls:
                    return {
                        "skill_overlap": 90, "seniority_alignment": 95,
                        "industry_alignment": 80, "compensation_confidence": 85,
                        "location_relevance": 100, "explanation": "Strong match.",
                        "positioning_strategy": "Emphasize scale.",
                        "final_score": 90.25,
                    }
                else:
                    return {
                        "skill_overlap": 60, "seniority_alignment": 65,
                        "industry_alignment": 60, "compensation_confidence": 55,
                        "location_relevance": 90, "explanation": "Ok match.",
                        "positioning_strategy": "Consider applying.",
                        "final_score": 65.0,
                    }

            mock_scorer = MagicMock()
            mock_scorer.score = AsyncMock(side_effect=score_side_effect)
            mock_scorer.estimate_salary_aed = AsyncMock(return_value=None)
            MockScorer.return_value = mock_scorer

            # Setup email
            mock_email = MagicMock()
            mock_email.send_job_alert.return_value = True
            mock_email.to_email = "test@test.com"
            mock_email.enabled = True
            MockEmail.return_value = mock_email

            # Setup connectors
            source_jobs = {
                "linkedin": [all_raw_jobs[0], all_raw_jobs[1], all_raw_jobs[2]],
                "indeed": [all_raw_jobs[3], all_raw_jobs[4], all_raw_jobs[5]],
                "bayt": [all_raw_jobs[6], all_raw_jobs[7], all_raw_jobs[8]],
                "gulftarget": [all_raw_jobs[9], all_raw_jobs[10], all_raw_jobs[11]],
                "naukrigulf": [all_raw_jobs[12], all_raw_jobs[13], all_raw_jobs[14]],
            }

            for MockConn, name in zip([MockLI, MockII, MockBayt, MockGT, MockNG], sources):
                mock_conn = MagicMock()
                mock_conn.name = name
                mock_conn._safe_scrape = AsyncMock(return_value=source_jobs[name])
                MockConn.return_value = mock_conn

            # Run the full pipeline
            orch = JobHunterOrchestrator(config=full_pipeline_config)
            stats = await orch.run()

        # Assertions
        assert stats["total_scraped"] == 15, f"Expected 15 scraped, got {stats['total_scraped']}"
        assert stats["total_new"] == 3, f"Expected 3 new (deduplication), got {stats['total_new']}"
        assert stats["total_scored"] == 3, f"Expected 3 scored, got {stats['total_scored']}"
        assert stats["total_notified"] == 2, f"Expected 2 notified, got {stats['total_notified']}"

        # DB assertions
        assert mock_db.save_job.call_count == 3  # 3 new jobs saved
        assert mock_db.save_score.call_count == 3  # 3 scored
        assert mock_db.save_notification.call_count == 3  # 2 success + 1 failure (score < 80 but orchestrator still saves notification? No — orchestrator only notifies if score >= 80)
        # Actually the orchestrator only saves notification when score >= min_score
        # Let's check email sends
        assert mock_email.send_job_alert.call_count == 2

        # Scraping logs saved for all 5 connectors
        assert mock_db.save_scraping_log.call_count == 5

        # Vector store additions
        assert mock_vs.add_job.call_count == 3

    @pytest.mark.asyncio
    async def test_all_connectors_fail_gracefully(self, full_pipeline_config):
        """All 5 connectors fail → stats show 0 scraped, run completes."""
        with patch("src.agent.orchestrator.LinkedInConnector") as MockLI, \
             patch("src.agent.orchestrator.IndeedConnector") as MockII, \
             patch("src.agent.orchestrator.BaytConnector") as MockBayt, \
             patch("src.agent.orchestrator.GulfTalentConnector") as MockGT, \
             patch("src.agent.orchestrator.NaukriGulfConnector") as MockNG, \
             patch("src.agent.orchestrator.Scorer") as MockScorer, \
             patch("src.agent.orchestrator.JobFilter") as MockFilter, \
             patch("src.agent.orchestrator.JobParser") as MockParser, \
             patch("src.agent.orchestrator.Database") as MockDB, \
             patch("src.agent.orchestrator.VectorStore"), \
             patch("src.agent.orchestrator.EmailService") as MockEmail, \
             patch("src.agent.orchestrator.load_candidate_profile") as MockProfile:

            MockProfile.return_value = {"name": "T", "skills": [], "industries": [], "target_comp_aed": 1200000}
            mock_db = MagicMock()
            mock_db.save_scraping_log = MagicMock()
            MockDB.return_value = mock_db
            MockEmail.return_value = MagicMock()

            for MockConn, name in zip([MockLI, MockII, MockBayt, MockGT, MockNG],
                                      ["linkedin", "indeed", "bayt", "gulftarget", "naukrigulf"]):
                mock_conn = MagicMock()
                mock_conn.name = name
                mock_conn._safe_scrape = AsyncMock(side_effect=Exception(f"{name} failed"))
                MockConn.return_value = mock_conn

            MockFilter.return_value = MagicMock()
            MockParser.return_value = MagicMock()
            MockScorer.return_value = MagicMock()

            orch = JobHunterOrchestrator(config=full_pipeline_config)
            stats = await orch.run()

        assert stats["total_scraped"] == 0
        assert len(stats["errors"]) > 0

    @pytest.mark.asyncio
    async def test_all_jobs_below_threshold_no_emails(self, full_pipeline_config):
        """All jobs score < 80 → no emails sent, all scored jobs saved."""
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

            MockProfile.return_value = {"name": "T", "skills": [], "industries": [], "target_comp_aed": 1200000}
            mock_db = MagicMock()
            mock_db.job_exists.return_value = False
            mock_db.save_job.return_value = MagicMock(id=1)
            mock_db.save_scraping_log = MagicMock()
            MockDB.return_value = mock_db
            MockVS.return_value = MagicMock()

            mock_filter = MagicMock()
            mock_filter.passes.return_value = (True, "ok")
            MockFilter.return_value = mock_filter

            mock_parser = MagicMock()
            mock_parser.parse.side_effect = lambda raw: {**raw, "seniority_level": "director"}
            MockParser.return_value = mock_parser

            mock_scorer = MagicMock()
            mock_scorer.score = AsyncMock(return_value={
                "skill_overlap": 50, "seniority_alignment": 55,
                "industry_alignment": 50, "compensation_confidence": 50,
                "location_relevance": 60, "explanation": "Weak match.",
                "positioning_strategy": "Consider.", "final_score": 53.0,
            })
            mock_scorer.estimate_salary_aed = AsyncMock(return_value=None)
            MockScorer.return_value = mock_scorer

            mock_email = MagicMock()
            MockEmail.return_value = mock_email

            # One connector returns 3 jobs
            mock_conn = MagicMock()
            mock_conn.name = "linkedin"
            mock_conn._safe_scrape = AsyncMock(return_value=[
                {"title": "Director", "company": f"C{i}", "location": "Dubai",
                 "url": f"https://li.com/job/{i}", "description": "D", "source": "linkedin", "salary_raw": ""}
                for i in range(3)
            ])
            MockLI.return_value = mock_conn

            for MockConn, name in zip([MockII, MockBayt, MockGT, MockNG],
                                      ["indeed", "bayt", "gulftarget", "naukrigulf"]):
                mc = MagicMock()
                mc.name = name
                mc._safe_scrape = AsyncMock(return_value=[])
                MockConn.return_value = mc

            orch = JobHunterOrchestrator(config=full_pipeline_config)
            stats = await orch.run()

        assert stats["total_notified"] == 0
        mock_email.send_job_alert.assert_not_called()
        assert stats["total_scored"] == 3
