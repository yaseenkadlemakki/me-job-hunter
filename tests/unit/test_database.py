"""Unit tests for src/storage/database.py"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from src.storage.database import Database, Job, ScoredJob, Notification, ScrapingLog


@pytest.fixture
def job_data():
    return {
        "source": "linkedin",
        "title": "Director of Engineering",
        "company": "Acme Corp",
        "location": "Dubai, UAE",
        "url": "https://linkedin.com/jobs/view/director-123",
        "description": "Great role for a director.",
        "salary_raw": "AED 1,200,000",
        "salary_estimated_aed": 1200000.0,
        "posted_date": datetime(2026, 3, 1),
        "status": "new",
    }


@pytest.fixture
def score_data():
    return {
        "final_score": 88.5,
        "skill_overlap": 90,
        "seniority_alignment": 92,
        "industry_alignment": 80,
        "compensation_confidence": 85,
        "location_relevance": 100,
        "explanation": "Strong match for Director role in Dubai.",
        "positioning_strategy": "Emphasize platform scale.",
    }


class TestInitDb:
    """Test database initialization."""

    def test_creates_tables(self, db):
        """init_db() creates all required tables."""
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        assert "jobs" in tables
        assert "scored_jobs" in tables
        assert "notifications" in tables
        assert "scraping_logs" in tables

    def test_idempotent_init(self, db):
        """Calling init_db() twice doesn't raise."""
        db.init_db()  # second call
        from sqlalchemy import inspect
        tables = inspect(db.engine).get_table_names()
        assert "jobs" in tables


class TestJobExists:
    """Test job_exists() method."""

    def test_new_url_returns_false(self, db, job_data):
        assert db.job_exists(job_data["url"]) is False

    def test_saved_url_returns_true(self, db, job_data):
        db.save_job(job_data)
        assert db.job_exists(job_data["url"]) is True

    def test_different_url_returns_false(self, db, job_data):
        db.save_job(job_data)
        assert db.job_exists("https://other.com/job/999") is False


class TestSaveJob:
    """Test save_job() method."""

    def test_saves_job_returns_job_object(self, db, job_data):
        result = db.save_job(job_data)
        assert result is not None
        assert isinstance(result, Job)

    def test_saved_job_has_id(self, db, job_data):
        result = db.save_job(job_data)
        assert result.id is not None
        assert result.id > 0

    def test_saved_job_has_correct_title(self, db, job_data):
        result = db.save_job(job_data)
        assert result.title == "Director of Engineering"

    def test_saved_job_has_correct_company(self, db, job_data):
        result = db.save_job(job_data)
        assert result.company == "Acme Corp"

    def test_saved_job_has_correct_location(self, db, job_data):
        result = db.save_job(job_data)
        assert result.location == "Dubai, UAE"

    def test_saved_job_has_correct_url(self, db, job_data):
        result = db.save_job(job_data)
        assert result.url == job_data["url"]

    def test_saved_job_has_status_new(self, db, job_data):
        result = db.save_job(job_data)
        assert result.status == "new"

    def test_duplicate_url_returns_none(self, db, job_data):
        db.save_job(job_data)
        result = db.save_job(job_data)
        assert result is None

    def test_saves_salary_raw(self, db, job_data):
        result = db.save_job(job_data)
        assert result.salary_raw == "AED 1,200,000"

    def test_saves_salary_estimated_aed(self, db, job_data):
        result = db.save_job(job_data)
        assert result.salary_estimated_aed == 1200000.0

    def test_saves_posted_date(self, db, job_data):
        result = db.save_job(job_data)
        assert result.posted_date == datetime(2026, 3, 1)


class TestSaveScore:
    """Test save_score() method."""

    def test_saves_score_returns_scored_job(self, db, job_data, score_data):
        job = db.save_job(job_data)
        result = db.save_score(job.id, score_data)
        assert isinstance(result, ScoredJob)

    def test_score_has_correct_relevance(self, db, job_data, score_data):
        job = db.save_job(job_data)
        result = db.save_score(job.id, score_data)
        assert result.relevance_score == 88.5

    def test_score_has_correct_skill_score(self, db, job_data, score_data):
        job = db.save_job(job_data)
        result = db.save_score(job.id, score_data)
        assert result.skill_score == 90

    def test_score_has_explanation(self, db, job_data, score_data):
        job = db.save_job(job_data)
        result = db.save_score(job.id, score_data)
        assert "Strong match" in result.explanation

    def test_score_has_positioning_strategy(self, db, job_data, score_data):
        job = db.save_job(job_data)
        result = db.save_score(job.id, score_data)
        assert "platform scale" in result.positioning_strategy


class TestSaveNotification:
    """Test save_notification() method."""

    def test_saves_notification(self, db, job_data):
        job = db.save_job(job_data)
        db.save_notification(job.id, "test@example.com", success=True)
        with db.session() as s:
            notif = s.query(Notification).filter(Notification.job_id == job.id).first()
            assert notif is not None
            assert notif.success is True

    def test_saves_failed_notification(self, db, job_data):
        job = db.save_job(job_data)
        db.save_notification(job.id, "test@example.com", success=False, error="SMTP error")
        with db.session() as s:
            notif = s.query(Notification).filter(Notification.job_id == job.id).first()
            assert notif.success is False
            assert "SMTP" in notif.error_message

    def test_saves_notification_email_to(self, db, job_data):
        job = db.save_job(job_data)
        db.save_notification(job.id, "yaseen@test.com", success=True)
        with db.session() as s:
            notif = s.query(Notification).filter(Notification.job_id == job.id).first()
            assert notif.email_to == "yaseen@test.com"


class TestSaveScrapingLog:
    """Test save_scraping_log() method."""

    def test_saves_scraping_log(self, db):
        db.save_scraping_log({
            "source": "linkedin",
            "jobs_found": 15,
            "jobs_new": 10,
            "jobs_scored": 5,
            "jobs_notified": 2,
            "duration_seconds": 45.3,
        })
        with db.session() as s:
            log = s.query(ScrapingLog).filter(ScrapingLog.source == "linkedin").first()
            assert log is not None
            assert log.jobs_found == 15
            assert log.jobs_new == 10
            assert log.jobs_scored == 5
            assert log.jobs_notified == 2

    def test_saves_scraping_log_with_errors(self, db):
        db.save_scraping_log({
            "source": "indeed",
            "jobs_found": 0,
            "errors": "Connection timeout",
            "duration_seconds": 5.0,
        })
        with db.session() as s:
            log = s.query(ScrapingLog).filter(ScrapingLog.source == "indeed").first()
            assert "timeout" in log.errors.lower()


class TestGetTopJobs:
    """Test get_top_jobs() method."""

    def _create_job_with_score(self, db, url, title, score):
        job = db.save_job({
            "source": "linkedin",
            "title": title,
            "company": "C",
            "location": "Dubai",
            "url": url,
            "description": "Test",
        })
        if job:
            db.save_score(job.id, {
                "final_score": score,
                "skill_overlap": score,
                "seniority_alignment": score,
                "industry_alignment": score,
                "compensation_confidence": score,
                "location_relevance": score,
                "explanation": "test",
                "positioning_strategy": "test",
            })
        return job

    def test_returns_top_jobs_ordered_by_score(self, db):
        self._create_job_with_score(db, "https://e.com/1", "Job A", 75.0)
        self._create_job_with_score(db, "https://e.com/2", "Job B", 90.0)
        self._create_job_with_score(db, "https://e.com/3", "Job C", 85.0)

        results = db.get_top_jobs(limit=10, min_score=80.0)
        scores = [r["relevance_score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_filters_below_min_score(self, db):
        self._create_job_with_score(db, "https://e.com/1", "Job A", 75.0)
        self._create_job_with_score(db, "https://e.com/2", "Job B", 90.0)

        results = db.get_top_jobs(min_score=80.0)
        assert all(r["relevance_score"] >= 80 for r in results)
        assert len(results) == 1

    def test_respects_limit(self, db):
        for i in range(5):
            self._create_job_with_score(db, f"https://e.com/{i}", f"Job {i}", 85.0 + i)

        results = db.get_top_jobs(limit=3, min_score=80.0)
        assert len(results) <= 3

    def test_returns_empty_when_no_jobs(self, db):
        results = db.get_top_jobs()
        assert results == []

    def test_results_include_required_fields(self, db):
        self._create_job_with_score(db, "https://e.com/1", "Director", 85.0)
        results = db.get_top_jobs(min_score=80.0)
        assert len(results) == 1
        job = results[0]
        assert "title" in job
        assert "company" in job
        assert "url" in job
        assert "relevance_score" in job


class TestGetStats:
    """Test get_stats() method."""

    def test_returns_stats_dict(self, db):
        stats = db.get_stats()
        assert isinstance(stats, dict)
        assert "total_jobs" in stats
        assert "scored_jobs" in stats
        assert "high_quality_jobs" in stats
        assert "notifications_sent" in stats

    def test_empty_db_stats(self, db):
        stats = db.get_stats()
        assert stats["total_jobs"] == 0
        assert stats["scored_jobs"] == 0
        assert stats["high_quality_jobs"] == 0

    def test_stats_after_adding_data(self, db, job_data, score_data):
        job = db.save_job(job_data)
        db.save_score(job.id, score_data)
        db.save_notification(job.id, "test@test.com", success=True)

        stats = db.get_stats()
        assert stats["total_jobs"] == 1
        assert stats["scored_jobs"] == 1
        assert stats["high_quality_jobs"] == 1  # score 88.5 >= 80
        assert stats["notifications_sent"] == 1


class TestGetJobByUrl:
    """Test get_job_by_url() method."""

    def test_returns_job_for_existing_url(self, db, job_data):
        db.save_job(job_data)
        result = db.get_job_by_url(job_data["url"])
        assert result is not None
        assert result.url == job_data["url"]

    def test_returns_none_for_unknown_url(self, db):
        result = db.get_job_by_url("https://nonexistent.com/job")
        assert result is None


class TestUpdateJobStatus:
    """Test update_job_status() method."""

    def test_updates_status(self, db, job_data):
        job = db.save_job(job_data)
        db.update_job_status(job.id, "scored")
        result = db.get_job_by_id(job.id)
        assert result.status == "scored"
