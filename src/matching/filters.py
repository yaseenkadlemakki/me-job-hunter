"""Pre-scoring filters for compensation, seniority, and location."""

from __future__ import annotations

import re
from typing import Optional

from src.utils.logger import setup_logger

logger = setup_logger("filters")

SENIORITY_LEVELS = {
    "executive": ["c-suite", "cto", "ceo", "chief", "evp", "president"],
    "vp": ["vp", "vice president", "svp", "avp", "vice-president"],
    "director": ["director", "head of", "senior director", "principal director"],
    "manager": ["manager", "lead", "principal", "staff"],
    "ic": ["engineer", "developer", "architect", "specialist", "analyst", "associate"],
}

SENIOR_ROLES = {"executive", "vp", "director"}

LOCATION_TIER = {
    "tier1": ["dubai", "abu dhabi", "riyadh"],
    "tier2": ["uae", "united arab emirates", "saudi arabia", "ksa"],
    "tier3": ["middle east", "doha", "qatar", "kuwait", "bahrain", "oman", "muscat"],
    "excluded": ["israel", "tel aviv"],
}


class JobFilter:
    """Filter jobs before expensive scoring."""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.filters_cfg = config.get("filters", {}) if config else {}

        self.target_locations = [l.lower() for l in self.filters_cfg.get("target_locations", [
            "dubai", "abu dhabi", "riyadh", "saudi arabia", "uae", "middle east"
        ])]
        self.target_titles = [t.lower() for t in self.filters_cfg.get("target_titles", [
            "director", "vp", "vice president", "head of", "cto"
        ])]
        self.excluded_locations = [l.lower() for l in self.filters_cfg.get("excluded_locations", ["israel"])]
        self.excluded_regions = [r.lower() for r in self.filters_cfg.get("excluded_regions", ["il"])]

    def passes(self, job_data: dict) -> tuple[bool, str]:
        """
        Check if a job passes all pre-scoring filters.
        Returns (passes: bool, reason: str).
        """
        title = (job_data.get("title") or "").lower()
        location = (job_data.get("location") or "").lower()
        description = (job_data.get("description") or "").lower()

        # Must have a title
        if not title:
            return False, "no title"

        # Excluded location check
        for exc in self.excluded_locations:
            if exc in location:
                return False, f"excluded location: {exc}"

        # Excluded region check
        for reg in self.excluded_regions:
            if f" {reg} " in f" {location} " or location.startswith(f"{reg} ") or location.endswith(f" {reg}"):
                return False, f"excluded region: {reg}"

        # Must be a senior role
        if not self._is_senior_role(title, description):
            return False, f"not a senior role: {title}"

        # Must match a target location (if we can determine location)
        if location and not self._matches_target_location(location):
            # Check description for location hints
            if not self._matches_target_location(description[:500]):
                return False, f"not in target location: {location}"

        return True, "ok"

    def _is_senior_role(self, title: str, description: str) -> bool:
        """Check if the role is at director/VP/executive level."""
        text = title  # primarily check title

        for level in SENIOR_ROLES:
            keywords = SENIORITY_LEVELS[level]
            if any(kw in text for kw in keywords):
                return True

        # Also check exact matches from config
        for target_title in self.target_titles:
            if target_title in text:
                return True

        return False

    def _matches_target_location(self, text: str) -> bool:
        """Check if location matches any target location."""
        for tier in ["tier1", "tier2", "tier3"]:
            for loc in LOCATION_TIER[tier]:
                if loc in text:
                    return True

        for target in self.target_locations:
            if target in text:
                return True

        return False

    def get_location_score(self, location: str) -> int:
        """Return a location quality score for quick ranking."""
        loc = location.lower()
        for excl in LOCATION_TIER["excluded"]:
            if excl in loc:
                return 0
        for t1 in LOCATION_TIER["tier1"]:
            if t1 in loc:
                return 100
        for t2 in LOCATION_TIER["tier2"]:
            if t2 in loc:
                return 80
        for t3 in LOCATION_TIER["tier3"]:
            if t3 in loc:
                return 60
        return 20

    def estimate_seniority_score(self, title: str) -> int:
        """Quick seniority score without LLM."""
        title_lower = title.lower()
        for kw in SENIORITY_LEVELS["executive"]:
            if kw in title_lower:
                return 95
        for kw in SENIORITY_LEVELS["vp"]:
            if kw in title_lower:
                return 90
        for kw in SENIORITY_LEVELS["director"]:
            if kw in title_lower:
                return 85
        for kw in SENIORITY_LEVELS["manager"]:
            if kw in title_lower:
                return 50
        return 30
