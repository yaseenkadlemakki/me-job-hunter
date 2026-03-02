"""Indeed UAE/Middle East scraper using Playwright."""

from __future__ import annotations

import asyncio
import random
import re
from typing import Optional
from urllib.parse import quote

from playwright.async_api import async_playwright

from src.connectors.base import BaseConnector
from src.utils.logger import setup_logger

logger = setup_logger("connector.indeed")


class IndeedConnector(BaseConnector):
    """Scrape Indeed (ae.indeed.com) job listings."""

    name = "indeed"
    base_url = "https://ae.indeed.com"

    async def scrape(self) -> list[dict]:
        jobs = []
        queries = self._build_queries()

        async with async_playwright() as pw:
            browser, context = await self._get_browser_context(pw)
            try:
                for title_q, location_q in queries:
                    try:
                        page_jobs = await self._scrape_query(context, title_q, location_q)
                        jobs.extend(page_jobs)
                        logger.info(f"[indeed] Query '{title_q}' in '{location_q}': {len(page_jobs)} jobs")
                    except Exception as e:
                        logger.warning(f"[indeed] Query failed ({title_q}, {location_q}): {e}")
                    await asyncio.sleep(random.uniform(2.0, 3.5))
            finally:
                await context.close()
                await browser.close()

        seen = set()
        unique = [j for j in jobs if j["url"] not in seen and not seen.add(j["url"])]
        logger.info(f"[indeed] Total unique jobs: {len(unique)}")
        return unique

    def _build_queries(self) -> list[tuple[str, str]]:
        filters = self.config.get("filters", {})
        titles = filters.get("target_titles", [
            "Director Engineering",
            "VP Engineering",
            "Head Engineering",
        ])
        # Indeed UAE, Saudi Arabia subdomain
        return [
            ("Director Engineering", "Dubai"),
            ("Head of Engineering", "Dubai"),
            ("VP Engineering", "Dubai"),
            ("Director Engineering", "Riyadh"),
            ("Head Platform", "Dubai"),
        ]

    async def _scrape_query(self, context, title: str, location: str) -> list[dict]:
        jobs = []
        max_pages = min(self.max_pages, 4)

        for page_num in range(max_pages):
            start = page_num * 10
            url = f"https://ae.indeed.com/jobs?q={quote(title)}&l={quote(location)}&start={start}&sort=date"

            # Also try Saudi Arabia subdomain for Riyadh
            if "riyadh" in location.lower() or "saudi" in location.lower():
                url = f"https://sa.indeed.com/jobs?q={quote(title)}&l={quote(location)}&start={start}&sort=date"

            await self.rate_limiter.wait(self.name)
            page = await context.new_page()
            try:
                success = await self._wait_for_page(page, url)
                if not success:
                    break

                # Handle CAPTCHA or bot detection
                if await self._is_blocked(page):
                    logger.warning(f"[indeed] Blocked by anti-bot on page {page_num}")
                    break

                await self._scroll_page(page)
                page_jobs = await self._extract_jobs(page, context)
                jobs.extend(page_jobs)

                if len(page_jobs) < 3:
                    break

                # Check for next page
                has_next = await page.query_selector('[data-testid="pagination-page-next"], a[aria-label="Next Page"]')
                if not has_next:
                    break

            finally:
                await page.close()

            await asyncio.sleep(random.uniform(1.5, 3.0))

        return jobs

    async def _is_blocked(self, page) -> bool:
        """Check if we've been blocked by anti-bot."""
        try:
            title = await page.title()
            content = await page.content()
            return "captcha" in title.lower() or "blocked" in title.lower() or "robot" in content.lower()
        except Exception:
            return False

    async def _scroll_page(self, page) -> None:
        for _ in range(3):
            await page.evaluate("window.scrollBy(0, 800)")
            await asyncio.sleep(0.4)

    async def _extract_jobs(self, page, context) -> list[dict]:
        jobs = []

        card_selectors = [
            ".job_seen_beacon",
            ".jobsearch-ResultsList > li",
            "[data-testid='slider_item']",
            ".tapItem",
        ]

        cards = []
        for sel in card_selectors:
            try:
                cards = await page.query_selector_all(sel)
                if cards:
                    break
            except Exception:
                continue

        logger.debug(f"[indeed] Found {len(cards)} cards")

        for card in cards[:20]:
            try:
                job = await self._parse_card(card)
                if job and job.get("url") and job.get("title"):
                    # Fetch description
                    job["description"] = await self._fetch_description(context, job["url"])
                    jobs.append(self._normalize_job(job))
            except Exception as e:
                logger.debug(f"[indeed] Card parse error: {e}")

        return jobs

    async def _parse_card(self, card) -> Optional[dict]:
        job = {}

        # Title
        try:
            el = await card.query_selector("h2.jobTitle > a, h2.jobTitle span, [data-testid='jobTitle']")
            if el:
                job["title"] = (await el.text_content() or "").strip()
        except Exception:
            pass

        # Company
        try:
            el = await card.query_selector("[data-testid='company-name'], .companyName, span.company")
            if el:
                job["company"] = (await el.text_content() or "").strip()
        except Exception:
            pass

        # Location
        try:
            el = await card.query_selector("[data-testid='text-location'], .companyLocation")
            if el:
                job["location"] = (await el.text_content() or "").strip()
        except Exception:
            pass

        # Salary
        try:
            el = await card.query_selector(".salary-snippet-container, .estimated-salary")
            if el:
                job["salary_raw"] = (await el.text_content() or "").strip()
        except Exception:
            pass

        # URL
        try:
            el = await card.query_selector("h2.jobTitle > a, a[id^='job_']")
            if el:
                href = await el.get_attribute("href")
                if href:
                    if href.startswith("/"):
                        href = f"https://ae.indeed.com{href}"
                    job["url"] = href.split("?")[0] if "vjk=" not in href else href
        except Exception:
            pass

        # Date
        try:
            el = await card.query_selector(".date, [data-testid='myJobsStateDate']")
            if el:
                job["posted_date"] = (await el.text_content() or "").strip()
        except Exception:
            pass

        if not job.get("title"):
            return None

        return job

    async def _fetch_description(self, context, job_url: str) -> str:
        """Fetch full job description."""
        try:
            await self.rate_limiter.wait(self.name)
            page = await context.new_page()
            try:
                await page.goto(job_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                await asyncio.sleep(random.uniform(1.0, 2.0))

                desc_selectors = [
                    "#jobDescriptionText",
                    ".jobsearch-jobDescriptionText",
                    "#job-description",
                    "[data-testid='jobsearch-JobComponent-description']",
                ]
                for sel in desc_selectors:
                    try:
                        el = await page.query_selector(sel)
                        if el:
                            text = await el.inner_text()
                            if text and len(text) > 50:
                                return text.strip()
                    except Exception:
                        pass
            finally:
                await page.close()
        except Exception as e:
            logger.debug(f"[indeed] Description fetch failed: {e}")
        return ""
