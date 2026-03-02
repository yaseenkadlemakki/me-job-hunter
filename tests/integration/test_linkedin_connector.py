"""Integration tests for the LinkedIn connector (mocked Playwright)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.connectors.linkedin import LinkedInConnector


@pytest.fixture
def connector(config):
    return LinkedInConnector(config=config)


def make_mock_card(title="Director of Engineering", company="Gulf Tech", location="Dubai, UAE",
                   url="https://linkedin.com/jobs/view/123"):
    """Create a mock Playwright card element."""
    card = AsyncMock()

    title_el = AsyncMock()
    title_el.text_content = AsyncMock(return_value=title)

    company_el = AsyncMock()
    company_el.text_content = AsyncMock(return_value=company)

    location_el = AsyncMock()
    location_el.text_content = AsyncMock(return_value=location)

    link_el = AsyncMock()
    link_el.get_attribute = AsyncMock(return_value=url)

    date_el = AsyncMock()
    date_el.get_attribute = AsyncMock(return_value="2026-03-01")
    date_el.text_content = AsyncMock(return_value="2 days ago")

    async def query_selector_side_effect(sel):
        if "title" in sel or "h3" in sel:
            return title_el
        if "company" in sel or "subtitle" in sel:
            return company_el
        if "location" in sel:
            return location_el
        if "full-link" in sel or "href" in sel or "job-card" in sel:
            return link_el
        if sel == "time":
            return date_el
        return None

    card.query_selector = AsyncMock(side_effect=query_selector_side_effect)
    return card


class TestLinkedInBuildQueries:
    """Test _build_queries() method."""

    def test_returns_list_of_tuples(self, connector):
        queries = connector._build_queries()
        assert isinstance(queries, list)
        assert all(isinstance(q, tuple) and len(q) == 2 for q in queries)

    def test_queries_include_target_titles(self, connector):
        queries = connector._build_queries()
        titles = [q[0] for q in queries]
        # Should include some senior titles
        assert any("Director" in t or "VP" in t or "Head" in t for t in titles)

    def test_queries_include_target_locations(self, connector):
        queries = connector._build_queries()
        locations = [q[1] for q in queries]
        assert any("Dubai" in l or "UAE" in l for l in locations)


class TestLinkedInConnectorName:
    def test_name_is_linkedin(self, connector):
        assert connector.name == "linkedin"

    def test_base_url(self, connector):
        assert "linkedin.com" in connector.base_url


class TestLinkedInScrape:
    """Test the scrape() method with mocked Playwright."""

    @pytest.mark.asyncio
    async def test_scrape_returns_list(self, connector):
        """scrape() returns a list (even if empty due to mocked playwright)."""
        with patch("src.connectors.linkedin.async_playwright") as mock_pw:
            mock_pw_instance = AsyncMock()
            mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_pw_instance)
            mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)

            browser = AsyncMock()
            context = AsyncMock()
            context.close = AsyncMock()
            browser.close = AsyncMock()
            browser.new_context = AsyncMock(return_value=context)
            context.add_init_script = AsyncMock()

            mock_pw_instance.chromium = AsyncMock()
            mock_pw_instance.chromium.launch = AsyncMock(return_value=browser)

            page = AsyncMock()
            page.goto = AsyncMock()
            page.wait_for_selector = AsyncMock()
            page.query_selector_all = AsyncMock(return_value=[])
            page.evaluate = AsyncMock()
            page.close = AsyncMock()
            context.new_page = AsyncMock(return_value=page)

            with patch.object(connector, "rate_limiter") as mock_rl:
                mock_rl.wait = AsyncMock()
                result = await connector.scrape()

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_safe_scrape_returns_empty_on_exception(self, connector):
        """_safe_scrape() returns [] if scrape() raises."""
        with patch.object(connector, "scrape", side_effect=Exception("Playwright error")):
            result = await connector._safe_scrape()
        assert result == []

    @pytest.mark.asyncio
    async def test_scrape_deduplicates_by_url(self, connector):
        """Returned jobs are deduplicated by URL."""
        with patch("src.connectors.linkedin.async_playwright") as mock_pw:
            mock_pw_instance = AsyncMock()
            mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_pw_instance)
            mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)

            browser = AsyncMock()
            context = AsyncMock()
            context.close = AsyncMock()
            browser.close = AsyncMock()
            browser.new_context = AsyncMock(return_value=context)
            context.add_init_script = AsyncMock()
            mock_pw_instance.chromium = AsyncMock()
            mock_pw_instance.chromium.launch = AsyncMock(return_value=browser)

            page = AsyncMock()
            page.goto = AsyncMock()
            page.wait_for_selector = AsyncMock()
            page.query_selector_all = AsyncMock(return_value=[])
            page.evaluate = AsyncMock()
            page.close = AsyncMock()
            context.new_page = AsyncMock(return_value=page)

            with patch.object(connector, "rate_limiter") as mock_rl:
                mock_rl.wait = AsyncMock()
                with patch.object(connector, "_scrape_query", AsyncMock(return_value=[
                    {"title": "Director", "company": "C", "location": "Dubai",
                     "url": "https://linkedin.com/jobs/1", "description": "", "source": "linkedin", "salary_raw": ""},
                    {"title": "Director", "company": "C", "location": "Dubai",
                     "url": "https://linkedin.com/jobs/1", "description": "", "source": "linkedin", "salary_raw": ""},  # duplicate
                ])):
                    result = await connector.scrape()

        urls = [j["url"] for j in result]
        assert len(urls) == len(set(urls))


class TestLinkedInNormalizeJob:
    """Test that scraper normalizes job dict properly."""

    def test_normalize_adds_source(self, connector):
        raw = {"title": "Director", "company": "C", "location": "Dubai", "url": "https://e.com"}
        normalized = connector._normalize_job(raw)
        assert normalized["source"] == "linkedin"

    def test_normalize_adds_missing_keys(self, connector):
        raw = {"title": "Director", "url": "https://e.com"}
        normalized = connector._normalize_job(raw)
        assert "company" in normalized
        assert "description" in normalized
        assert "salary_raw" in normalized

    def test_rate_limiter_configured(self, connector):
        assert connector.rate_limiter is not None


class TestLinkedInEncode:
    """Test URL encoding."""

    def test_encode_spaces(self, connector):
        encoded = connector._encode("Director of Engineering")
        assert " " not in encoded
        assert "Director" in encoded
