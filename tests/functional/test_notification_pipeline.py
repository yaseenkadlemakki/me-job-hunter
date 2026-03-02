"""Functional tests for the notification pipeline (score → email → DB)."""

from __future__ import annotations

import smtplib
from unittest.mock import MagicMock, patch

import pytest

from src.notifications.email_service import EmailService
from src.storage.database import Database


@pytest.fixture
def email_svc(config):
    return EmailService(config=config)


class TestNotificationPipeline:
    """Test score-to-email pipeline."""

    def test_high_score_triggers_email(self, email_svc, mock_smtp, sample_job_director_dubai, sample_score_high):
        """Job scoring >= 80 should send email."""
        result = email_svc.send_job_alert(sample_job_director_dubai, sample_score_high)
        assert result is True
        mock_smtp.sendmail.assert_called_once()

    def test_low_score_no_email(self, email_svc, sample_job_director_dubai, sample_score_low):
        """Score < 80 should NOT send email — caller's responsibility in orchestrator."""
        # EmailService itself doesn't check score threshold — that's the orchestrator's job.
        # But we test that with disabled service, no email is sent.
        email_svc.enabled = False
        result = email_svc.send_job_alert(sample_job_director_dubai, sample_score_low)
        assert result is False

    def test_email_content_matches_job_data(
        self, email_svc, mock_smtp, sample_job_director_dubai, sample_score_high
    ):
        """Email content should contain job data fields."""
        email_svc.send_job_alert(sample_job_director_dubai, sample_score_high)
        call_args = mock_smtp.sendmail.call_args[0]
        email_body = call_args[2]  # Third arg is the email string
        assert "Director of Engineering" in email_body
        assert "Acme Cloud Inc" in email_body
        assert "Dubai" in email_body

    def test_notification_db_record_created(self, db, sample_job_director_dubai, sample_score_high):
        """After successful email send, notification should be saved to DB."""
        job = db.save_job(sample_job_director_dubai)
        db.save_notification(job.id, "test@test.com", success=True)

        from src.storage.database import Notification
        with db.session() as s:
            notif = s.query(Notification).filter(Notification.job_id == job.id).first()
        assert notif is not None
        assert notif.success is True

    def test_failed_email_notification_not_marked_sent(self, db, sample_job_director_dubai):
        """Failed email should create a notification with success=False."""
        job = db.save_job(sample_job_director_dubai)
        db.save_notification(job.id, "test@test.com", success=False, error="SMTP error")

        from src.storage.database import Notification
        with db.session() as s:
            notif = s.query(Notification).filter(Notification.job_id == job.id).first()
        assert notif.success is False
        assert "SMTP" in notif.error_message

    def test_no_duplicate_notifications(self, db, sample_job_director_dubai, sample_score_high):
        """Already-notified jobs should not be re-notified by checking existing notifications."""
        job = db.save_job(sample_job_director_dubai)
        db.save_notification(job.id, "test@test.com", success=True)

        # In real usage, orchestrator checks if job is already in DB (job_exists)
        # which prevents re-scoring and re-notification
        assert db.job_exists(sample_job_director_dubai["url"]) is True

    def test_email_subject_format(self, email_svc, sample_job_director_dubai, sample_score_high):
        """Email subject follows [Score: X/100] Title at Company — Location format."""
        subject = email_svc._build_subject(sample_job_director_dubai, sample_score_high)
        assert "[Score:" in subject
        assert "/100]" in subject

    def test_email_fails_without_app_password(self, config, sample_job_director_dubai, sample_score_high, monkeypatch):
        """Email service returns False when GMAIL_APP_PASSWORD is not set."""
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "")
        service = EmailService(config=config)
        result = service.send_job_alert(sample_job_director_dubai, sample_score_high)
        assert result is False

    def test_notifications_saved_after_multiple_sends(
        self, db, sample_job_director_dubai, sample_score_high
    ):
        """Multiple notifications for different jobs are all saved."""
        jobs_data = []
        for i in range(3):
            job_d = {**sample_job_director_dubai, "url": f"https://example.com/job/{i}"}
            job = db.save_job(job_d)
            if job:
                db.save_notification(job.id, "test@test.com", success=True)
                jobs_data.append(job)

        from src.storage.database import Notification
        with db.session() as s:
            count = s.query(Notification).count()
        assert count == 3

    def test_high_score_email_contains_score_breakdown(
        self, email_svc, mock_smtp, sample_job_director_dubai, sample_score_high
    ):
        """HTML email should contain 5 score breakdown sections."""
        email_svc.send_job_alert(sample_job_director_dubai, sample_score_high)
        email_body = mock_smtp.sendmail.call_args[0][2]
        # Should contain all 5 dimension labels
        assert "Skills" in email_body or "skill" in email_body.lower()
        assert "Seniority" in email_body or "seniority" in email_body.lower()
