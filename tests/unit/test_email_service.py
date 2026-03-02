"""Unit tests for src/notifications/email_service.py"""

from __future__ import annotations

import smtplib
from unittest.mock import MagicMock, patch, call

import pytest

from src.notifications.email_service import EmailService, _comp_display


@pytest.fixture
def email_service(config):
    return EmailService(config=config)


@pytest.fixture
def email_service_no_password(config, monkeypatch):
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "")
    return EmailService(config=config)


class TestCompDisplay:
    """Test the _comp_display helper function."""

    def test_both_salary_raw_and_aed(self):
        result = _comp_display("AED 1,200,000 - 1,500,000", 1350000.0)
        assert "AED 1,200,000 - 1,500,000" in result
        assert "1,350,000 AED/yr" in result

    def test_only_salary_raw(self):
        result = _comp_display("AED 1,200,000", None)
        assert "AED 1,200,000" in result

    def test_only_aed(self):
        result = _comp_display(None, 1350000.0)
        assert "1,350,000 AED/yr" in result

    def test_neither_returns_not_disclosed(self):
        result = _comp_display(None, None)
        assert result == "Not disclosed"


class TestBuildSubject:
    """Test _build_subject() method."""

    def test_subject_includes_score(self, email_service, sample_job_director_dubai, sample_score_high):
        subject = email_service._build_subject(sample_job_director_dubai, sample_score_high)
        assert "90" in subject or "Score:" in subject

    def test_subject_includes_title(self, email_service, sample_job_director_dubai, sample_score_high):
        subject = email_service._build_subject(sample_job_director_dubai, sample_score_high)
        assert "Director of Engineering" in subject

    def test_subject_includes_company(self, email_service, sample_job_director_dubai, sample_score_high):
        subject = email_service._build_subject(sample_job_director_dubai, sample_score_high)
        assert "Acme Cloud Inc" in subject

    def test_subject_includes_location(self, email_service, sample_job_director_dubai, sample_score_high):
        subject = email_service._build_subject(sample_job_director_dubai, sample_score_high)
        assert "Dubai" in subject

    def test_subject_format(self, email_service, sample_job_director_dubai, sample_score_high):
        subject = email_service._build_subject(sample_job_director_dubai, sample_score_high)
        assert subject.startswith("[Score:")


class TestBuildHtmlBody:
    """Test _build_html_body() method."""

    def test_html_contains_title(self, email_service, sample_job_director_dubai, sample_score_high):
        html = email_service._build_html_body(sample_job_director_dubai, sample_score_high)
        assert "Director of Engineering" in html

    def test_html_contains_company(self, email_service, sample_job_director_dubai, sample_score_high):
        html = email_service._build_html_body(sample_job_director_dubai, sample_score_high)
        assert "Acme Cloud Inc" in html

    def test_html_contains_location(self, email_service, sample_job_director_dubai, sample_score_high):
        html = email_service._build_html_body(sample_job_director_dubai, sample_score_high)
        assert "Dubai" in html

    def test_html_contains_score(self, email_service, sample_job_director_dubai, sample_score_high):
        html = email_service._build_html_body(sample_job_director_dubai, sample_score_high)
        assert "90" in html

    def test_html_contains_source(self, email_service, sample_job_director_dubai, sample_score_high):
        html = email_service._build_html_body(sample_job_director_dubai, sample_score_high)
        assert "linkedin" in html.lower() or "LinkedIn" in html

    def test_html_contains_explanation(self, email_service, sample_job_director_dubai, sample_score_high):
        html = email_service._build_html_body(sample_job_director_dubai, sample_score_high)
        assert "Strong match" in html

    def test_html_contains_positioning_strategy(self, email_service, sample_job_director_dubai, sample_score_high):
        html = email_service._build_html_body(sample_job_director_dubai, sample_score_high)
        assert "Highlight Juniper" in html

    def test_html_contains_job_url(self, email_service, sample_job_director_dubai, sample_score_high):
        html = email_service._build_html_body(sample_job_director_dubai, sample_score_high)
        assert sample_job_director_dubai["url"] in html

    def test_high_score_green_badge(self, email_service, sample_job_director_dubai, sample_score_high):
        html = email_service._build_html_body(sample_job_director_dubai, sample_score_high)
        assert "#27ae60" in html  # Green for >= 90

    def test_mid_score_orange_badge(self, email_service, sample_job_director_dubai):
        score = {"final_score": 82, "skill_overlap": 80, "seniority_alignment": 80,
                 "industry_alignment": 80, "compensation_confidence": 80,
                 "location_relevance": 90, "explanation": "Ok", "positioning_strategy": "Ok"}
        html = email_service._build_html_body(sample_job_director_dubai, score)
        assert "#f39c12" in html  # Orange for 80-89

    def test_low_score_red_badge(self, email_service, sample_job_director_dubai, sample_score_low):
        html = email_service._build_html_body(sample_job_director_dubai, sample_score_low)
        assert "#e74c3c" in html  # Red for < 80

    def test_html_contains_score_breakdown(self, email_service, sample_job_director_dubai, sample_score_high):
        html = email_service._build_html_body(sample_job_director_dubai, sample_score_high)
        # Should have all 5 score dimensions
        assert "Skills" in html
        assert "Seniority" in html
        assert "Industry" in html
        assert "Comp" in html
        assert "Location" in html

    def test_html_truncates_long_description(self, email_service, sample_score_high):
        job = {
            "title": "Director",
            "company": "C",
            "location": "Dubai",
            "url": "https://example.com",
            "source": "linkedin",
            "description": "x" * 5000,
            "salary_raw": None,
            "salary_estimated_aed": None,
        }
        html = email_service._build_html_body(job, sample_score_high)
        assert "..." in html


class TestBuildTextBody:
    """Test _build_text_body() method."""

    def test_text_contains_title(self, email_service, sample_job_director_dubai, sample_score_high):
        text = email_service._build_text_body(sample_job_director_dubai, sample_score_high)
        assert "Director of Engineering" in text

    def test_text_contains_company(self, email_service, sample_job_director_dubai, sample_score_high):
        text = email_service._build_text_body(sample_job_director_dubai, sample_score_high)
        assert "Acme Cloud Inc" in text

    def test_text_contains_score(self, email_service, sample_job_director_dubai, sample_score_high):
        text = email_service._build_text_body(sample_job_director_dubai, sample_score_high)
        assert "90" in text

    def test_text_contains_url(self, email_service, sample_job_director_dubai, sample_score_high):
        text = email_service._build_text_body(sample_job_director_dubai, sample_score_high)
        assert sample_job_director_dubai["url"] in text

    def test_text_contains_score_breakdown(self, email_service, sample_job_director_dubai, sample_score_high):
        text = email_service._build_text_body(sample_job_director_dubai, sample_score_high)
        assert "Skills:" in text
        assert "Seniority:" in text


class TestSendJobAlert:
    """Test send_job_alert() method."""

    def test_sends_email_on_success(
        self, email_service, mock_smtp, sample_job_director_dubai, sample_score_high
    ):
        result = email_service.send_job_alert(sample_job_director_dubai, sample_score_high)
        assert result is True
        mock_smtp.sendmail.assert_called_once()

    def test_skips_when_no_password(
        self, email_service_no_password, sample_job_director_dubai, sample_score_high
    ):
        result = email_service_no_password.send_job_alert(sample_job_director_dubai, sample_score_high)
        assert result is False

    def test_returns_false_when_disabled(self, config, sample_job_director_dubai, sample_score_high):
        config["notifications"]["send_email"] = False
        service = EmailService(config=config)
        result = service.send_job_alert(sample_job_director_dubai, sample_score_high)
        assert result is False

    def test_returns_false_on_auth_error(
        self, email_service, monkeypatch, sample_job_director_dubai, sample_score_high
    ):
        smtp_instance = MagicMock()
        smtp_instance.__enter__ = MagicMock(return_value=smtp_instance)
        smtp_instance.__exit__ = MagicMock(return_value=False)
        smtp_instance.ehlo = MagicMock()
        smtp_instance.starttls = MagicMock()
        smtp_instance.login = MagicMock(side_effect=smtplib.SMTPAuthenticationError(535, "Auth failed"))

        monkeypatch.setattr(smtplib, "SMTP", MagicMock(return_value=smtp_instance))
        result = email_service.send_job_alert(sample_job_director_dubai, sample_score_high)
        assert result is False

    def test_returns_false_on_smtp_error(
        self, email_service, monkeypatch, sample_job_director_dubai, sample_score_high
    ):
        smtp_instance = MagicMock()
        smtp_instance.__enter__ = MagicMock(return_value=smtp_instance)
        smtp_instance.__exit__ = MagicMock(return_value=False)
        smtp_instance.ehlo = MagicMock()
        smtp_instance.starttls = MagicMock()
        smtp_instance.login = MagicMock(side_effect=smtplib.SMTPException("connection failed"))

        monkeypatch.setattr(smtplib, "SMTP", MagicMock(return_value=smtp_instance))
        result = email_service.send_job_alert(sample_job_director_dubai, sample_score_high)
        assert result is False


class TestSendTestEmail:
    """Test send_test_email() method."""

    def test_sends_test_email(self, email_service, mock_smtp):
        result = email_service.send_test_email()
        assert result is True
        mock_smtp.sendmail.assert_called_once()

    def test_test_email_subject(self, email_service, mock_smtp):
        email_service.send_test_email()
        # Check the MIME message contained the right subject
        sendmail_args = mock_smtp.sendmail.call_args[0]
        assert "Test Email" in sendmail_args[2]


class TestSendDigest:
    """Test send_digest() method."""

    def test_empty_jobs_returns_false(self, email_service):
        result = email_service.send_digest([])
        assert result is False

    def test_sends_digest_with_jobs(self, email_service, mock_smtp):
        jobs = [
            {"title": "Director", "company": "C", "location": "Dubai", "url": "https://e.com/1", "relevance_score": 85},
            {"title": "VP", "company": "D", "location": "Abu Dhabi", "url": "https://e.com/2", "relevance_score": 90},
        ]
        result = email_service.send_digest(jobs)
        assert result is True

    def test_digest_subject_includes_count(self, email_service, mock_smtp):
        jobs = [{"title": "D", "company": "C", "location": "Dubai", "url": "https://e.com", "relevance_score": 85}]
        email_service.send_digest(jobs)
        sendmail_args = mock_smtp.sendmail.call_args[0]
        assert "1" in sendmail_args[2]
