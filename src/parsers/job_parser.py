"""Extract structured data from raw job HTML/text."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional
from bs4 import BeautifulSoup

from src.utils.logger import setup_logger

logger = setup_logger("job_parser")

# Salary patterns (AED, USD, SAR, QAR)
SALARY_PATTERNS = [
    # AED ranges
    r"(?:AED|aed)\s*[\d,]+\s*[-–to]+\s*[\d,]+(?:\s*(?:AED|aed))?",
    r"[\d,]+\s*[-–to]+\s*[\d,]+\s*(?:AED|aed)",
    # USD ranges
    r"(?:USD|\$)\s*[\d,]+(?:k|K)?\s*[-–to]+\s*[\d,]+(?:k|K)?",
    r"[\d,]+(?:k|K)?\s*[-–to]+\s*[\d,]+(?:k|K)?\s*(?:USD|\$)",
    # SAR ranges
    r"(?:SAR|sar)\s*[\d,]+\s*[-–to]+\s*[\d,]+",
    # Monthly/yearly hints
    r"[\d,]+(?:\s*(?:AED|USD|SAR|QAR))?(?:\s*per\s*(?:month|year|annum))",
]

# Seniority keywords
SENIOR_KEYWORDS = {
    "executive": ["c-suite", "cto", "ceo", "coo", "chief", "president", "evp"],
    "vp": ["vp", "vice president", "svp", "avp"],
    "director": ["director", "head of", "senior director", "principal director"],
    "manager": ["manager", "lead", "principal", "staff"],
    "ic": ["engineer", "developer", "architect", "specialist", "analyst"],
}


class JobParser:
    """Parse raw job data into structured format."""

    def parse(self, raw: dict) -> dict:
        """Parse and normalize a raw job dict."""
        description = raw.get("description") or ""
        cleaned_desc = self._clean_html(description)

        salary_raw = raw.get("salary_raw") or self._extract_salary(cleaned_desc)
        salary_aed = self._estimate_salary_aed(salary_raw, raw.get("location", ""))

        posted_date = self._parse_date(raw.get("posted_date"))
        seniority = self._detect_seniority(raw.get("title", ""), cleaned_desc)

        return {
            "source": raw.get("source", "unknown"),
            "title": self._clean_text(raw.get("title", "")),
            "company": self._clean_text(raw.get("company", "")),
            "location": self._clean_text(raw.get("location", "")),
            "url": raw.get("url", ""),
            "description": cleaned_desc,
            "salary_raw": salary_raw,
            "salary_estimated_aed": salary_aed,
            "posted_date": posted_date,
            "seniority_level": seniority,
        }

    def _clean_html(self, text: str) -> str:
        """Strip HTML tags and clean whitespace."""
        if not text:
            return ""
        try:
            soup = BeautifulSoup(text, "lxml")
            clean = soup.get_text(separator=" ")
        except Exception:
            clean = re.sub(r"<[^>]+>", " ", text)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    def _clean_text(self, text: str) -> str:
        if not text:
            return ""
        return re.sub(r"\s+", " ", text).strip()

    def _extract_salary(self, text: str) -> Optional[str]:
        if not text:
            return None
        for pattern in SALARY_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0).strip()
        return None

    def _estimate_salary_aed(self, salary_raw: Optional[str], location: str) -> Optional[float]:
        """Convert raw salary string to estimated AED value."""
        if not salary_raw:
            return None
        try:
            # Extract numbers
            numbers = re.findall(r"[\d,]+(?:\.\d+)?", salary_raw.replace(",", ""))
            numbers = [float(n) for n in numbers if n]
            if not numbers:
                return None

            amount = sum(numbers) / len(numbers)  # take midpoint of range

            # Detect currency and period
            salary_upper = salary_raw.upper()

            # Handle K suffix
            if re.search(r"\d\s*[kK]", salary_raw):
                amount *= 1000

            # Convert to AED
            if "USD" in salary_upper or "$" in salary_upper:
                # Monthly to annual, then to AED
                if "MONTH" in salary_upper or amount < 50000:
                    amount *= 12
                amount *= 3.67  # USD to AED
            elif "SAR" in salary_upper:
                if "MONTH" in salary_upper or amount < 200000:
                    amount *= 12
                amount *= 0.98  # SAR to AED (approx)
            elif "QAR" in salary_upper:
                if "MONTH" in salary_upper or amount < 200000:
                    amount *= 12
                amount *= 1.01  # QAR to AED (approx)
            else:
                # Assume AED
                if "MONTH" in salary_upper or amount < 500000:
                    amount *= 12

            return round(amount, 0)
        except Exception:
            return None

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        if not date_str:
            return None
        try:
            # Relative dates: "2 days ago", "1 week ago"
            date_str = str(date_str).strip().lower()
            now = datetime.utcnow()

            if "just now" in date_str or "today" in date_str:
                return now
            if "yesterday" in date_str:
                return now - timedelta(days=1)

            match = re.search(r"(\d+)\s*(hour|day|week|month)", date_str)
            if match:
                n = int(match.group(1))
                unit = match.group(2)
                if "hour" in unit:
                    return now - timedelta(hours=n)
                if "day" in unit:
                    return now - timedelta(days=n)
                if "week" in unit:
                    return now - timedelta(weeks=n)
                if "month" in unit:
                    return now - timedelta(days=n * 30)

            # Try common date formats
            for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%B %d, %Y", "%d %B %Y"]:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
        except Exception:
            pass
        return None

    def _detect_seniority(self, title: str, description: str) -> str:
        """Detect seniority level from title and description."""
        text = (title + " " + description[:500]).lower()
        for level, keywords in SENIOR_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return level
        return "unknown"
