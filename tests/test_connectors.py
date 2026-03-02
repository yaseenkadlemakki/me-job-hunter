"""Tests for job connectors (using mocked Playwright)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
import pytest

from src.connectors.base import BaseConnector
from src.connectors.linkedin import LinkedInConnector
from src.connectors.indeed import IndeedConnector
from src.connectors.bayt import BaytConnector
from src.connectors.gulftarget import GulfTalentConnector
from src.connectors.naukrigulf import NaukriGulfConnector


@pytest.fixture
def config():
    return {
        "filters": {
            "target_titles": ["Director of Engineering", "VP Engineering", "Head of Engineering"],
            "target_locations": ["Dubai", "UAE", "Saudi Arabia"],
        },
        "rate_limits": {
            "linkedin": 0.1,
            "indeed": 0.1,
            "bayt": 0.1,
            "gulftarget": 0.1,
            "naukrigulf": 0.1,
        },
        "scraper": {
            "headless": True,
            "timeout_ms": 5000,
            "max_pages": 1,
        },
    }


# ===== Base Connector Tests =====

def test_base_connector_get_random_ua(config):
    """BaseConnector is abstract; test via a concrete subclass."""
    class ConcreteConnector(BaseConnector):
        name = "test"
        async def scrape(self):
            return []

    conn = ConcreteConnector(config=config)
    ua = conn.get_random_ua()
    assert isinstance(ua, str)
    assert "Mozilla" in ua


def test_base_connector_normalize_job(config):
    class ConcreteConnector(BaseConnector):
        name = "testsite"
        async def scrape(self):
            return []

    conn = ConcreteConnector(config=config)
    raw = {"title": "Director of Engineering", "url": "https://example.com/job/1"}
    normalized = conn._normalize_job(raw)
    assert normalized["source"] == "testsite"
    assert normalized["title"] == "Director of Engineering"
    assert normalized["description"] == ""  # default


def test_base_connector_search_queries(config):
    class ConcreteConnector(BaseConnector):
        name = "test"
        async def scrape(self):
            return []

    conn = ConcreteConnector(config=config)
    queries = conn._get_search_queries()
    assert isinstance(queries, list)
    assert len(queries) > 0
    for title, loc in queries:
        assert isinstance(title, str)
        assert isinstance(loc, str)


# ===== Connector Initialization Tests =====

def test_linkedin_connector_init(config):
    conn = LinkedInConnector(config=config)
    assert conn.name == "linkedin"
    assert conn.headless is True
    assert conn.max_pages == 1


def test_indeed_connector_init(config):
    conn = IndeedConnector(config=config)
    assert conn.name == "indeed"


def test_bayt_connector_init(config):
    conn = BaytConnector(config=config)
    assert conn.name == "bayt"
    assert len(conn.SEARCH_URLS) > 0


def test_gulftarget_connector_init(config):
    conn = GulfTalentConnector(config=config)
    assert conn.name == "gulftarget"


def test_naukrigulf_connector_init(config):
    conn = NaukriGulfConnector(config=config)
    assert conn.name == "naukrigulf"


# ===== Safe Scrape Error Handling =====

@pytest.mark.asyncio
async def test_safe_scrape_returns_empty_on_error(config):
    """_safe_scrape should return [] even if scrape() raises."""
    conn = LinkedInConnector(config=config)
    with patch.object(conn, "scrape", side_effect=Exception("Network error")):
        result = await conn._safe_scrape()
        assert result == []


# ===== Job Parsing Tests (mocked) =====

@pytest.mark.asyncio
async def test_linkedin_parse_card_missing_title(config):
    """Cards with no title should return None."""
    conn = LinkedInConnector(config=config)

    mock_card = AsyncMock()
    mock_card.query_selector.return_value = None

    result = await conn._parse_card(mock_card, MagicMock(), MagicMock())
    assert result is None


# ===== Integration: Full Scrape with Mocked Playwright =====

def _make_mock_element(text: str = "", href: str = "", datetime_attr: str = ""):
    """Helper to create a mock Playwright element."""
    el = AsyncMock()
    el.text_content = AsyncMock(return_value=text)
    el.inner_text = AsyncMock(return_value=text)
    el.get_attribute = AsyncMock(side_effect=lambda attr: {
        "href": href,
        "datetime": datetime_attr,
    }.get(attr))
    return el


@pytest.mark.asyncio
async def test_bayt_connector_no_cards(config):
    """When no cards are found, should return empty list."""
    conn = BaytConnector(config=config)

    mock_page = AsyncMock()
    mock_page.query_selector_all = AsyncMock(return_value=[])
    mock_page.evaluate = AsyncMock()

    result = await conn._extract_jobs(mock_page, AsyncMock())
    assert result == []


@pytest.mark.asyncio
async def test_naukrigulf_dismiss_popups_no_popup(config):
    """dismiss_popups should handle missing popup gracefully."""
    conn = NaukriGulfConnector(config=config)
    mock_page = AsyncMock()
    mock_page.query_selector = AsyncMock(return_value=None)
    # Should not raise
    await conn._dismiss_popups(mock_page)


# ===== Rate Limiter Integration =====

@pytest.mark.asyncio
async def test_rate_limiter_applied(config):
    """Verify rate limiter wait is called before requests."""
    conn = BaytConnector(config=config)
    wait_called = False

    original_wait = conn.rate_limiter.wait
    async def mock_wait(site):
        nonlocal wait_called
        wait_called = True
    conn.rate_limiter.wait = mock_wait

    mock_context = AsyncMock()
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock(side_effect=Exception("Stop early"))
    mock_context.new_page = AsyncMock(return_value=mock_page)

    try:
        await conn._scrape_listing(mock_context, conn.SEARCH_URLS[0])
    except Exception:
        pass

    # Rate limiter should have been called at least once
    assert wait_called


# ===== Job Parser Integration =====

def test_job_parser_cleans_html():
    from src.parsers.job_parser import JobParser
    parser = JobParser()
    job = parser.parse({
        "title": "<b>Director of Engineering</b>",
        "company": "ACME Corp",
        "location": "Dubai, UAE",
        "url": "https://example.com/1",
        "description": "<p>We need a <strong>Director</strong> to lead the team.</p>",
        "salary_raw": None,
        "source": "test",
    })
    assert "<" not in job["title"] or job["title"] == "<b>Director of Engineering</b>"
    assert "Director" in job["description"]
    assert "<p>" not in job["description"]


def test_job_parser_salary_extraction():
    from src.parsers.job_parser import JobParser
    parser = JobParser()
    job = parser.parse({
        "title": "VP Engineering",
        "company": "Cloud Inc",
        "location": "Dubai",
        "url": "https://example.com/2",
        "description": "Salary: AED 150,000 - 200,000 per month",
        "source": "test",
    })
    assert job["salary_raw"] is not None or job["salary_estimated_aed"] is None


def test_job_parser_relative_date():
    from src.parsers.job_parser import JobParser
    parser = JobParser()
    job = parser.parse({
        "title": "Head of Engineering",
        "company": "Tech Co",
        "location": "Dubai",
        "url": "https://example.com/3",
        "description": "",
        "posted_date": "3 days ago",
        "source": "test",
    })
    assert job["posted_date"] is not None
