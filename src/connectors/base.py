"""Abstract base connector for job scrapers."""

from __future__ import annotations

import random
import asyncio
from abc import ABC, abstractmethod
from typing import Optional

from src.utils.logger import setup_logger
from src.utils.rate_limiter import get_rate_limiter

logger = setup_logger("connector.base")

DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
]


class BaseConnector(ABC):
    """Abstract base class for all job site connectors."""

    name: str = "base"
    base_url: str = ""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.rate_limiter = get_rate_limiter(config)
        self.scraper_cfg = config.get("scraper", {}) if config else {}
        self.user_agents = self.scraper_cfg.get("user_agents", DEFAULT_USER_AGENTS)
        self.headless = self.scraper_cfg.get("headless", True)
        self.timeout_ms = self.scraper_cfg.get("timeout_ms", 30000)
        self.max_pages = self.scraper_cfg.get("max_pages", 5)
        self._browser = None
        self._playwright = None

    def get_random_ua(self) -> str:
        return random.choice(self.user_agents)

    async def _get_browser_context(self, playwright):
        """Create a browser context with realistic fingerprinting."""
        browser = await playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
                "--window-size=1920,1080",
            ],
        )
        context = await browser.new_context(
            user_agent=self.get_random_ua(),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Upgrade-Insecure-Requests": "1",
            },
        )

        # Inject anti-detection scripts
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            window.chrome = { runtime: {} };
        """)
        return browser, context

    @abstractmethod
    async def scrape(self) -> list[dict]:
        """Scrape jobs. Returns list of job dicts."""
        pass

    async def _safe_scrape(self) -> list[dict]:
        """Wrapper that catches all exceptions."""
        try:
            return await self.scrape()
        except Exception as e:
            logger.error(f"[{self.name}] Scrape failed: {e}", exc_info=True)
            return []

    def _get_search_queries(self) -> list[tuple[str, str]]:
        """Return (title_query, location) tuples from config."""
        filters = self.config.get("filters", {})
        titles = filters.get("target_titles", ["Director Engineering", "VP Engineering", "Head of Engineering"])
        locations = filters.get("target_locations", ["Dubai", "UAE"])

        # Build representative queries (top 3 titles × top 3 locations to avoid too many)
        key_titles = titles[:3]
        key_locations = [l for l in locations if l in ("Dubai", "UAE", "Saudi Arabia", "Riyadh")][:2] or locations[:2]

        queries = []
        for title in key_titles:
            for loc in key_locations:
                queries.append((title, loc))
        return queries

    async def _wait_for_page(self, page, url: str) -> bool:
        """Navigate to URL and wait for load. Returns True on success."""
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            await asyncio.sleep(random.uniform(1.0, 2.5))  # human-like pause
            return True
        except Exception as e:
            logger.warning(f"[{self.name}] Failed to load {url}: {e}")
            return False

    def _normalize_job(self, raw: dict) -> dict:
        """Add source field and ensure required keys exist."""
        raw["source"] = self.name
        for key in ["title", "company", "location", "url", "description", "salary_raw"]:
            raw.setdefault(key, "")
        return raw
