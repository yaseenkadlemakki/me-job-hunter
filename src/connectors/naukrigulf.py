"""Naukrigulf scraper using Playwright."""

from __future__ import annotations

import asyncio
import random
from typing import Optional
from urllib.parse import quote

from playwright.async_api import async_playwright

from src.connectors.base import BaseConnector
from src.utils.logger import setup_logger

logger = setup_logger("connector.naukrigulf")


class NaukriGulfConnector(BaseConnector):
    """Scrape Naukrigulf job listings."""

    name = "naukrigulf"
    base_url = "https://www.naukrigulf.com"

    SEARCH_URLS = [
        "https://www.naukrigulf.com/director-engineering-jobs-in-uae",
        "https://www.naukrigulf.com/head-of-engineering-jobs-in-uae",
        "https://www.naukrigulf.com/vp-engineering-jobs-in-uae",
        "https://www.naukrigulf.com/director-engineering-jobs-in-saudi-arabia",
        "https://www.naukrigulf.com/head-platform-engineering-jobs-in-uae",
        "https://www.naukrigulf.com/cto-jobs-in-uae",
        "https://www.naukrigulf.com/head-of-devops-jobs-in-uae",
    ]

    async def scrape(self) -> list[dict]:
        jobs = []

        async with async_playwright() as pw:
            browser, context = await self._get_browser_context(pw)
            try:
                for url in self.SEARCH_URLS:
                    try:
                        page_jobs = await self._scrape_listing(context, url)
                        jobs.extend(page_jobs)
                        logger.info(f"[naukrigulf] {url}: {len(page_jobs)} jobs")
                    except Exception as e:
                        logger.warning(f"[naukrigulf] Failed: {url}: {e}")
                    await asyncio.sleep(random.uniform(2.0, 3.5))
            finally:
                await context.close()
                await browser.close()

        seen = set()
        unique = [j for j in jobs if j["url"] not in seen and not seen.add(j["url"])]
        logger.info(f"[naukrigulf] Total unique jobs: {len(unique)}")
        return unique

    async def _scrape_listing(self, context, listing_url: str) -> list[dict]:
        jobs = []
        max_pages = min(self.max_pages, 3)

        for page_num in range(1, max_pages + 1):
            url = listing_url if page_num == 1 else f"{listing_url}-{page_num}"

            await self.rate_limiter.wait(self.name)
            page = await context.new_page()
            try:
                success = await self._wait_for_page(page, url)
                if not success:
                    break

                # Handle cookie consent / popups
                await self._dismiss_popups(page)
                await self._scroll_page(page)

                page_jobs = await self._extract_jobs(page, context)
                jobs.extend(page_jobs)

                if len(page_jobs) < 3:
                    break

            finally:
                await page.close()

            await asyncio.sleep(random.uniform(1.5, 2.5))

        return jobs

    async def _dismiss_popups(self, page) -> None:
        """Dismiss cookie consent or other popups."""
        popup_selectors = [
            "button[id*='accept']",
            "button[class*='accept']",
            ".cookie-consent button",
            "#onetrust-accept-btn-handler",
        ]
        for sel in popup_selectors:
            try:
                btn = await page.query_selector(sel)
                if btn:
                    await btn.click()
                    await asyncio.sleep(0.5)
                    break
            except Exception:
                pass

    async def _scroll_page(self, page) -> None:
        for _ in range(4):
            await page.evaluate("window.scrollBy(0, 700)")
            await asyncio.sleep(0.4)

    async def _extract_jobs(self, page, context) -> list[dict]:
        jobs = []

        card_selectors = [
            ".list-job-bx",
            ".ng-Job",
            "article[class*='job']",
            ".job-listings li",
            "[class*='jobCard']",
            ".job_listing",
        ]

        cards = []
        for sel in card_selectors:
            try:
                cards = await page.query_selector_all(sel)
                if cards:
                    break
            except Exception:
                continue

        logger.debug(f"[naukrigulf] Found {len(cards)} cards")

        for card in cards[:20]:
            try:
                job = await self._parse_card(card)
                if job and job.get("url") and job.get("title"):
                    job["description"] = await self._fetch_description(context, job["url"])
                    jobs.append(self._normalize_job(job))
            except Exception as e:
                logger.debug(f"[naukrigulf] Card parse error: {e}")

        return jobs

    async def _parse_card(self, card) -> Optional[dict]:
        job = {}

        # Title + URL
        title_selectors = [
            "h2 a", "h3 a", "a[class*='title']",
            ".jobtitle a", ".job-title a",
            "a[href*='/jobs/']",
        ]
        for sel in title_selectors:
            try:
                el = await card.query_selector(sel)
                if el:
                    job["title"] = (await el.text_content() or "").strip()
                    href = await el.get_attribute("href")
                    if href:
                        job["url"] = href if href.startswith("http") else f"https://www.naukrigulf.com{href}"
                    break
            except Exception:
                pass

        # Company
        company_selectors = [
            ".company-name", ".companyName", "a[class*='company']",
            "[class*='employer']", "span[class*='comp']",
        ]
        for sel in company_selectors:
            try:
                el = await card.query_selector(sel)
                if el:
                    text = (await el.text_content() or "").strip()
                    if text and len(text) > 1:
                        job["company"] = text
                        break
            except Exception:
                pass

        # Location
        loc_selectors = [
            ".location", "[class*='location']", "li[class*='loc']",
            "span[class*='city']",
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
            el = await card.query_selector(".salary, [class*='salary']")
            if el:
                job["salary_raw"] = (await el.text_content() or "").strip()
        except Exception:
            pass

        # Date
        try:
            el = await card.query_selector("time, .date, [class*='date']")
            if el:
                job["posted_date"] = (
                    await el.get_attribute("datetime") or
                    (await el.text_content() or "").strip()
                )
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
                await self._dismiss_popups(page)

                desc_selectors = [
                    ".job-desc", "#job-desc", ".jobDescription",
                    "[class*='description']", ".job-details",
                    ".job_description",
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
            logger.debug(f"[naukrigulf] Description fetch failed: {e}")
        return ""
