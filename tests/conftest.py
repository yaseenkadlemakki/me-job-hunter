"""Shared pytest fixtures for the ME Job Hunter test suite."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.storage.database import Base, Database, Job, ScoredJob, Notification, ScrapingLog


# ── Event loop ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ── Database ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    """In-memory SQLite Database instance, fresh per test."""
    database = Database(url="sqlite:///:memory:")
    database.init_db()
    return database


@pytest.fixture
def db_session(db):
    """Provide a SQLAlchemy session for direct model manipulation in tests."""
    with db.session() as session:
        yield session


# ── Config ────────────────────────────────────────────────────────────────────

@pytest.fixture
def config():
    """Minimal test configuration dict mirroring config.yaml structure."""
    return {
        "candidate": {
            "name": "Yaseen Kadlemakki",
            "email": "yaseenkadlemakki@gmail.com",
            "target_comp_aed": 1200000,
        },
        "filters": {
            "min_relevance_score": 80,
            "target_locations": ["dubai", "abu dhabi", "riyadh", "saudi arabia", "uae", "middle east"],
            "target_titles": ["director", "vp", "vice president", "head of", "cto"],
            "excluded_locations": ["israel"],
            "excluded_regions": ["il"],
        },
        "scoring_weights": {
            "skill_overlap": 0.30,
            "seniority_alignment": 0.25,
            "industry_alignment": 0.15,
            "compensation_confidence": 0.15,
            "location_relevance": 0.15,
        },
        "scheduler": {
            "interval_hours": 6,
            "max_jobs_per_run": 50,
        },
        "llm": {
            "scoring_model": "claude-3-5-haiku-20241022",
            "temperature": 0.1,
            "max_tokens": 2048,
        },
        "rate_limits": {
            "linkedin": 3.0,
            "indeed": 2.0,
            "bayt": 2.0,
            "gulftarget": 2.0,
            "naukrigulf": 2.0,
        },
        "scraper": {
            "headless": True,
            "timeout_ms": 30000,
            "max_pages": 3,
        },
        "notifications": {
            "send_email": True,
            "min_score_for_email": 80,
        },
        "database": {
            "url": "sqlite:///:memory:",
        },
        "vector_store": {
            "persist_directory": "/tmp/test_chroma",
            "collection_name": "test_job_postings",
        },
    }


# ── Candidate profile ─────────────────────────────────────────────────────────

@pytest.fixture
def candidate_profile():
    """Yaseen's candidate profile as a fixture."""
    return {
        "name": "Yaseen Kadlemakki",
        "email": "yaseenkadlemakki@gmail.com",
        "linkedin": "https://www.linkedin.com/in/yaseenkadlemakki/",
        "current_role": "Director of Engineering",
        "current_company": "Juniper Networks",
        "location": "Greater Boston, MA",
        "target_location": "Middle East (UAE, Saudi Arabia)",
        "current_comp_usd": 600000,
        "target_comp_aed": 1200000,
        "years_experience": 15,
        "team_size": 75,
        "skills": [
            "Cloud Architecture (AWS)", "Kubernetes", "DevOps", "SRE",
            "Platform Engineering", "AI/ML", "MLOps", "CrewAI",
            "CI/CD", "Terraform", "Infrastructure as Code",
            "Developer Productivity", "Python", "Go",
            "Engineering Leadership", "Team Building",
        ],
        "industries": [
            "Enterprise SaaS", "Networking", "Cloud Infrastructure",
            "Datacenter", "Telecommunications", "Software Development",
        ],
        "education": [
            {"degree": "MBA", "institution": "University of New Hampshire"},
            {"degree": "B.E.", "institution": "Visvesvaraya Technological University"},
        ],
        "target_roles": [
            "Director of Engineering", "VP of Engineering",
            "Head of Engineering", "CTO",
        ],
        "key_achievements": [
            "Led 75+ engineers across multi-geo teams",
            "Built and scaled platform engineering organization at Juniper Networks",
        ],
        "summary": (
            "Seasoned engineering executive with 15+ years. Director of Engineering at "
            "Juniper Networks leading 75+ engineers. Seeking VP/Director role in UAE/Saudi Arabia."
        ),
    }


# ── Sample jobs ───────────────────────────────────────────────────────────────

@pytest.fixture
def sample_job_director_dubai():
    """High-scoring job: Director-level in Dubai with matching skills."""
    return {
        "source": "linkedin",
        "title": "Director of Engineering",
        "company": "Acme Cloud Inc",
        "location": "Dubai, UAE",
        "url": "https://linkedin.com/jobs/view/director-engineering-dubai-123",
        "description": (
            "We are seeking an experienced Director of Engineering to lead our cloud platform team. "
            "Requirements: 10+ years experience, Kubernetes, AWS, DevOps, Platform Engineering, "
            "Team leadership of 50+ engineers, Experience with CI/CD, Terraform, Microservices. "
            "Compensation: 1,400,000 AED per year. Location: Dubai Internet City."
        ),
        "salary_raw": "AED 1,200,000 - 1,500,000",
        "salary_estimated_aed": 1350000.0,
        "posted_date": datetime(2026, 3, 1),
        "seniority_level": "director",
    }


@pytest.fixture
def sample_job_ic_israel():
    """Low-scoring / filtered job: IC-level, Israel location."""
    return {
        "source": "linkedin",
        "title": "Senior Software Engineer",
        "company": "Tech Corp",
        "location": "Tel Aviv, Israel",
        "url": "https://linkedin.com/jobs/view/engineer-israel-456",
        "description": "Senior Software Engineer role. Python, backend development.",
        "salary_raw": None,
        "salary_estimated_aed": None,
        "posted_date": datetime(2026, 3, 1),
        "seniority_level": "ic",
    }


@pytest.fixture
def sample_job_no_salary():
    """Director job in Riyadh with no salary listed."""
    return {
        "source": "bayt",
        "title": "Head of Platform Engineering",
        "company": "Saudi Telecom",
        "location": "Riyadh, Saudi Arabia",
        "url": "https://bayt.com/jobs/head-platform-riyadh-789",
        "description": (
            "Head of Platform Engineering to lead 40+ engineer team. "
            "Requirements: Kubernetes, AWS, DevOps, Python, CI/CD. "
            "Great compensation package."
        ),
        "salary_raw": None,
        "salary_estimated_aed": None,
        "posted_date": datetime(2026, 2, 28),
        "seniority_level": "director",
    }


@pytest.fixture
def sample_score_high():
    """High-scoring score dict (>= 80)."""
    return {
        "skill_overlap": 90,
        "seniority_alignment": 95,
        "industry_alignment": 80,
        "compensation_confidence": 85,
        "location_relevance": 100,
        "explanation": "Strong match: Director-level role in Dubai with AWS/Kubernetes requirements.",
        "positioning_strategy": "Highlight Juniper platform scale and UAE compensation familiarity.",
        "final_score": 90.25,
    }


@pytest.fixture
def sample_score_low():
    """Low-scoring score dict (< 50)."""
    return {
        "skill_overlap": 30,
        "seniority_alignment": 20,
        "industry_alignment": 30,
        "compensation_confidence": 20,
        "location_relevance": 0,
        "explanation": "Poor match: IC-level role in Israel, skills mismatch.",
        "positioning_strategy": "Not recommended.",
        "final_score": 21.25,
    }


# ── Mock Claude client ────────────────────────────────────────────────────────

@pytest.fixture
def mock_claude_response_high():
    """Mock Claude API response for a high-scoring job."""
    return json.dumps({
        "skill_overlap": 90,
        "seniority_alignment": 95,
        "industry_alignment": 80,
        "compensation_confidence": 85,
        "location_relevance": 100,
        "explanation": "Strong match for Director of Engineering with AWS/Kubernetes.",
        "positioning_strategy": "Emphasize Juniper scale and platform expertise.",
    })


@pytest.fixture
def mock_claude_response_low():
    """Mock Claude API response for a low-scoring job."""
    return json.dumps({
        "skill_overlap": 30,
        "seniority_alignment": 20,
        "industry_alignment": 30,
        "compensation_confidence": 20,
        "location_relevance": 0,
        "explanation": "Poor match: wrong seniority, wrong location.",
        "positioning_strategy": "Not recommended.",
    })


@pytest.fixture
def mock_claude_client(mock_claude_response_high):
    """Mock Anthropic client that returns a valid high-score response."""
    mock_content = MagicMock()
    mock_content.text = mock_claude_response_high

    mock_response = MagicMock()
    mock_response.content = [mock_content]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    return mock_client


# ── Mock SMTP ────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_smtp(monkeypatch):
    """Mock smtplib.SMTP to prevent real email sending."""
    smtp_instance = MagicMock()
    smtp_instance.__enter__ = MagicMock(return_value=smtp_instance)
    smtp_instance.__exit__ = MagicMock(return_value=False)
    smtp_instance.ehlo = MagicMock()
    smtp_instance.starttls = MagicMock()
    smtp_instance.login = MagicMock()
    smtp_instance.sendmail = MagicMock()

    import smtplib
    monkeypatch.setattr(smtplib, "SMTP", MagicMock(return_value=smtp_instance))
    return smtp_instance


# ── Mock Playwright ───────────────────────────────────────────────────────────

@pytest.fixture
def mock_playwright_page():
    """Mock Playwright page object."""
    page = AsyncMock()
    page.goto = AsyncMock(return_value=None)
    page.wait_for_selector = AsyncMock(return_value=None)
    page.query_selector_all = AsyncMock(return_value=[])
    page.query_selector = AsyncMock(return_value=None)
    page.evaluate = AsyncMock(return_value=None)
    page.content = AsyncMock(return_value="<html><body></body></html>")
    page.close = AsyncMock(return_value=None)
    return page


@pytest.fixture
def mock_playwright_context(mock_playwright_page):
    """Mock Playwright browser context."""
    context = AsyncMock()
    context.new_page = AsyncMock(return_value=mock_playwright_page)
    context.close = AsyncMock(return_value=None)
    context.add_init_script = AsyncMock(return_value=None)
    return context


@pytest.fixture
def mock_playwright_browser(mock_playwright_context):
    """Mock Playwright browser."""
    browser = AsyncMock()
    browser.new_context = AsyncMock(return_value=mock_playwright_context)
    browser.close = AsyncMock(return_value=None)
    return browser


# ── Env vars ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def set_test_env(monkeypatch):
    """Set required environment variables for all tests."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-api-key-12345")
    monkeypatch.setenv("GMAIL_FROM", "test@gmail.com")
    monkeypatch.setenv("GMAIL_TO", "test@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "test-app-password")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
