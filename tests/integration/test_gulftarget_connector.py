"""Integration tests for the GulfTalent connector (mocked Playwright)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.connectors.gulftarget import GulfTalentConnector


@pytest.fixture
def connector(config):
    return GulfTalentConnector(config=config)


class TestGulfTalentBasics:
    def test_name_is_gulftarget(self, connector):
        assert connector.name == "gulftarget"

    def test_has_search_urls(self, connector):
        assert hasattr(connector, "SEARCH_URLS")
        assert len(connector.SEARCH_URLS) > 0

    def test_search_urls_target_gulftalent(self, connector):
        urls = " ".join(connector.SEARCH_URLS).lower()
        assert "gulftalent" in urls

    def test_rate_limiter_configured(self, connector):
        assert connector.rate_limiter is not None


class TestGulfTalentScrape:
    @pytest.mark.asyncio
    async def test_safe_scrape_returns_list(self, connector):
        with patch.object(connector, "scrape", AsyncMock(return_value=[])):
            result = await connector._safe_scrape()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_safe_scrape_handles_exception(self, connector):
        with patch.object(connector, "scrape", side_effect=Exception("Error")):
            result = await connector._safe_scrape()
        assert result == []

    @pytest.mark.asyncio
    async def test_empty_page_returns_empty_list(self, connector):
        with patch("src.connectors.gulftarget.async_playwright") as mock_pw:
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


class TestGulfTalentNormalization:
    def test_normalize_adds_source(self, connector):
        raw = {"title": "VP Engineering", "company": "C", "location": "Dubai", "url": "https://gulftalent.com/job/1"}
        normalized = connector._normalize_job(raw)
        assert normalized["source"] == "gulftarget"
