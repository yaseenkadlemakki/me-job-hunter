"""LinkedIn Jobs scraper using Playwright."""

from __future__ import annotations

import asyncio
import random
import re
from typing import Optional

from playwright.async_api import async_playwright

from src.connectors.base import BaseConnector
from src.utils.logger import setup_logger

logger = setup_logger("connector.linkedin")


class LinkedInConnector(BaseConnector):
    """Scrape LinkedIn Jobs (public search, no auth required)."""

    name = "linkedin"
    base_url = "https://www.linkedin.com/jobs/search/"

    async def scrape(self) -> list[dict]:
        """Scrape LinkedIn job listings."""
        jobs = []
        queries = self._build_queries()

        async with async_playwright() as pw:
            browser, context = await self._get_browser_context(pw)
            try:
                for title_q, location_q in queries:
                    try:
                        page_jobs = await self._scrape_query(context, title_q, location_q)
                        jobs.extend(page_jobs)
                        logger.info(f"[linkedin] Query '{title_q}' in '{location_q}': {len(page_jobs)} jobs")
                    except Exception as e:
                        logger.warning(f"[linkedin] Query failed ({title_q}, {location_q}): {e}")
                    await asyncio.sleep(random.uniform(2.0, 4.0))
            finally:
                await context.close()
                await browser.close()

        # Deduplicate by URL
        seen = set()
        unique = []
        for j in jobs:
            if j["url"] not in seen and j["url"]:
                seen.add(j["url"])
                unique.append(j)

        logger.info(f"[linkedin] Total unique jobs scraped: {len(unique)}")
        return unique

    def _build_queries(self) -> list[tuple[str, str]]:
        filters = self.config.get("filters", {})
        titles = filters.get("target_titles", [
            "Director of Engineering",
            "VP Engineering",
            "Head of Engineering",
            "Head of Platform",
            "Head of Infrastructure",
        ])
        locations = ["Dubai", "United Arab Emirates", "Riyadh", "Saudi Arabia"]

        key_titles = titles[:5]
        key_locs = locations[:3]
        return [(t, l) for t in key_titles[:2] for l in key_locs[:2]]

    async def _scrape_query(self, context, title: str, location: str) -> list[dict]:
        """Scrape one search query across multiple pages."""
        jobs = []
        max_pages = min(self.max_pages, 3)  # LinkedIn paginates by 25

        for page_num in range(max_pages):
            start = page_num * 25
            url = (
                f"https://www.linkedin.com/jobs/search/"
                f"?keywords={self._encode(title)}&location={self._encode(location)}&start={start}"
                f"&f_TPR=r604800"  # posted in last week
            )

            await self.rate_limiter.wait(self.name)
            page = await context.new_page()
            try:
                success = await self._wait_for_page(page, url)
                if not success:
                    break

                # Scroll to load all jobs
                await self._scroll_page(page)

                page_jobs = await self._extract_jobs_from_page(page, context)
                jobs.extend(page_jobs)

                if len(page_jobs) < 5:
                    break  # No more results

            finally:
                await page.close()

        return jobs

    async def _scroll_page(self, page) -> None:
        """Scroll down to trigger lazy loading."""
        for _ in range(5):
            await page.evaluate("window.scrollBy(0, 600)")
            await asyncio.sleep(0.5)

    async def _extract_jobs_from_page(self, page, context) -> list[dict]:
        """Extract job cards from the current search results page."""
        jobs = []
        try:
            # Wait for job listings to appear
            await page.wait_for_selector("ul.jobs-search__results-list, .jobs-search-results-list", timeout=10000)
        except Exception:
            logger.debug("[linkedin] Job list selector not found")

        # Try multiple selectors
        card_selectors = [
            "li.jobs-search-results__list-item",
            ".job-search-card",
            "li[class*='result']",
            ".base-card",
        ]

        cards = []
        for selector in card_selectors:
            try:
                cards = await page.query_selector_all(selector)
                if cards:
                    break
            except Exception:
                continue

        logger.debug(f"[linkedin] Found {len(cards)} job cards")

        for card in cards[:25]:
            try:
                job = await self._parse_card(card, page, context)
                if job and job.get("url"):
                    jobs.append(self._normalize_job(job))
            except Exception as e:
                logger.debug(f"[linkedin] Card parse error: {e}")

        return jobs

    async def _parse_card(self, card, page, context) -> Optional[dict]:
        """Parse a single job card."""
        job = {}

        # Title
        title_selectors = [
            "h3.base-search-card__title",
            ".job-search-card__title",
            "h3[class*='title']",
            "a[class*='title']",
        ]
        for sel in title_selectors:
            try:
                el = await card.query_selector(sel)
                if el:
                    job["title"] = (await el.text_content() or "").strip()
                    break
            except Exception:
                pass

        # Company
        company_selectors = [
            "h4.base-search-card__subtitle",
            ".job-search-card__company-name",
            "a[class*='company']",
            "h4[class*='company']",
        ]
        for sel in company_selectors:
            try:
                el = await card.query_selector(sel)
                if el:
                    job["company"] = (await el.text_content() or "").strip()
                    break
            except Exception:
                pass

        # Location
        loc_selectors = [
            ".job-search-card__location",
            "span[class*='location']",
            ".base-search-card__metadata span",
        ]
        for sel in loc_selectors:
            try:
                el = await card.query_selector(sel)
                if el:
                    job["location"] = (await el.text_content() or "").strip()
                    break
            except Exception:
                pass

        # URL
        link_selectors = ["a.base-card__full-link", "a[class*='job-card']", "a[href*='/jobs/view/']"]
        for sel in link_selectors:
            try:
                el = await card.query_selector(sel)
                if el:
                    href = await el.get_attribute("href")
                    if href:
                        job["url"] = href.split("?")[0] if "?" in href else href
                        break
            except Exception:
                pass

        # Posted date
        try:
            date_el = await card.query_selector("time")
            if date_el:
                job["posted_date"] = await date_el.get_attribute("datetime") or await date_el.text_content()
        except Exception:
            pass

        if not job.get("title") or not job.get("url"):
            return None

        # Fetch job description
        if job.get("url"):
            job["description"] = await self._fetch_job_description(context, job["url"])

        return job

    async def _fetch_job_description(self, context, job_url: str) -> str:
        """Fetch the full job description from the job detail page."""
        try:
            await self.rate_limiter.wait(self.name)
            page = await context.new_page()
            try:
                await page.goto(job_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                await asyncio.sleep(random.uniform(1.0, 2.0))

                # Try to expand description
                try:
                    expand_btn = await page.query_selector("button.show-more-less-html__button")
                    if expand_btn:
                        await expand_btn.click()
                        await asyncio.sleep(0.5)
                except Exception:
                    pass

                desc_selectors = [
                    ".show-more-less-html__markup",
                    ".description__text",
                    "#job-details",
                    ".job-details-jobs-unified-top-card__job-insight",
                    "[class*='description']",
                ]
                for sel in desc_selectors:
                    try:
                        el = await page.query_selector(sel)
                        if el:
                            text = await el.inner_text()
                            if text and len(text) > 100:
                                return text.strip()
                    except Exception:
                        pass
            finally:
                await page.close()
        except Exception as e:
            logger.debug(f"[linkedin] Description fetch failed for {job_url}: {e}")
        return ""

    def _encode(self, text: str) -> str:
        from urllib.parse import quote
        return quote(text)
