"""GulfTalent scraper using Playwright."""

from __future__ import annotations

import asyncio
import random
from typing import Optional
from urllib.parse import quote

from playwright.async_api import async_playwright

from src.connectors.base import BaseConnector
from src.utils.logger import setup_logger

logger = setup_logger("connector.gulftarget")


class GulfTalentConnector(BaseConnector):
    """Scrape GulfTalent job listings."""

    name = "gulftarget"
    base_url = "https://www.gulftalent.com"

    SEARCH_URLS = [
        "https://www.gulftalent.com/jobs?q=Director+of+Engineering",
        "https://www.gulftalent.com/jobs?q=Head+of+Engineering",
        "https://www.gulftalent.com/jobs?q=VP+Engineering",
        "https://www.gulftalent.com/jobs?q=Head+of+Platform+Engineering",
        "https://www.gulftalent.com/jobs?q=Director+Technology",
        "https://www.gulftalent.com/jobs?q=Head+of+Infrastructure",
        "https://www.gulftalent.com/jobs?q=Head+of+DevOps",
    ]

    async def scrape(self) -> list[dict]:
        jobs = []

        async with async_playwright() as pw:
            browser, context = await self._get_browser_context(pw)
            try:
                for url in self.SEARCH_URLS:
                    try:
                        page_jobs = await self._scrape_search(context, url)
                        jobs.extend(page_jobs)
                        logger.info(f"[gulftarget] {url}: {len(page_jobs)} jobs")
                    except Exception as e:
                        logger.warning(f"[gulftarget] Failed: {url}: {e}")
                    await asyncio.sleep(random.uniform(2.0, 3.5))
            finally:
                await context.close()
                await browser.close()

        seen = set()
        unique = [j for j in jobs if j["url"] not in seen and not seen.add(j["url"])]
        logger.info(f"[gulftarget] Total unique jobs: {len(unique)}")
        return unique

    async def _scrape_search(self, context, search_url: str) -> list[dict]:
        jobs = []
        max_pages = min(self.max_pages, 3)

        for page_num in range(1, max_pages + 1):
            url = search_url if page_num == 1 else f"{search_url}&page={page_num}"

            await self.rate_limiter.wait(self.name)
            page = await context.new_page()
            try:
                success = await self._wait_for_page(page, url)
                if not success:
                    break

                await self._scroll_page(page)
                page_jobs = await self._extract_jobs(page, context)
                jobs.extend(page_jobs)

                if len(page_jobs) < 3:
                    break

            finally:
                await page.close()

            await asyncio.sleep(random.uniform(1.5, 2.5))

        return jobs

    async def _scroll_page(self, page) -> None:
        for _ in range(4):
            await page.evaluate("window.scrollBy(0, 700)")
            await asyncio.sleep(0.4)

    async def _extract_jobs(self, page, context) -> list[dict]:
        jobs = []

        card_selectors = [
            ".job-listing",
            ".vacancy-item",
            ".gt-job",
            "article[class*='job']",
            "[class*='job-card']",
            ".search-result",
        ]

        cards = []
        for sel in card_selectors:
            try:
                cards = await page.query_selector_all(sel)
                if cards:
                    break
            except Exception:
                continue

        logger.debug(f"[gulftarget] Found {len(cards)} cards")

        for card in cards[:20]:
            try:
                job = await self._parse_card(card)
                if job and job.get("url") and job.get("title"):
                    job["description"] = await self._fetch_description(context, job["url"])
                    jobs.append(self._normalize_job(job))
            except Exception as e:
                logger.debug(f"[gulftarget] Card parse error: {e}")

        return jobs

    async def _parse_card(self, card) -> Optional[dict]:
        job = {}

        # Title + URL (often together in an anchor)
        title_selectors = [
            "h2 a", "h3 a", "h4 a",
            ".job-title a", ".vacancy-title a",
            "a[class*='title']", "a[href*='/jobs/']",
        ]
        for sel in title_selectors:
            try:
                el = await card.query_selector(sel)
                if el:
                    job["title"] = (await el.text_content() or "").strip()
                    href = await el.get_attribute("href")
                    if href:
                        job["url"] = href if href.startswith("http") else f"https://www.gulftalent.com{href}"
                    break
            except Exception:
                pass

        # Company
        company_selectors = [
            ".company-name", ".employer-name", "a[class*='company']",
            "[class*='employer']", "[class*='company']",
        ]
        for sel in company_selectors:
            try:
                el = await card.query_selector(sel)
                if el:
                    text = (await el.text_content() or "").strip()
                    if text:
                        job["company"] = text
                        break
            except Exception:
                pass

        # Location
        loc_selectors = [
            ".location", "[class*='location']", "[class*='city']",
            "span[class*='loc']",
        ]
        for sel in loc_selectors:
            try:
                el = await card.query_selector(sel)
                if el:
                    job["location"] = (await el.text_content() or "").strip()
                    break
            except Exception:
                pass

        # Salary
        try:
            el = await card.query_selector(".salary, [class*='salary'], [class*='comp']")
            if el:
                job["salary_raw"] = (await el.text_content() or "").strip()
        except Exception:
            pass

        if not job.get("title"):
            return None
        return job

    async def _fetch_description(self, context, job_url: str) -> str:
        try:
            await self.rate_limiter.wait(self.name)
            page = await context.new_page()
            try:
                await page.goto(job_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                await asyncio.sleep(random.uniform(1.0, 2.0))

                desc_selectors = [
                    ".job-description", "#job-description", ".vacancy-description",
                    "[class*='description']", ".content",
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
            logger.debug(f"[gulftarget] Description fetch failed: {e}")
        return ""
