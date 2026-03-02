"""Unit tests for src/matching/filters.py"""

from __future__ import annotations

import pytest

from src.matching.filters import JobFilter, SENIORITY_LEVELS, LOCATION_TIER


@pytest.fixture
def job_filter(config):
    return JobFilter(config=config)


@pytest.fixture
def job_filter_default():
    return JobFilter()


class TestPasses:
    """Test the main passes() filter method."""

    def test_director_dubai_passes(self, job_filter):
        job = {"title": "Director of Engineering", "location": "Dubai, UAE", "description": ""}
        result, reason = job_filter.passes(job)
        assert result is True
        assert reason == "ok"

    def test_vp_riyadh_passes(self, job_filter):
        job = {"title": "VP of Engineering", "location": "Riyadh, Saudi Arabia", "description": ""}
        result, reason = job_filter.passes(job)
        assert result is True

    def test_head_of_abu_dhabi_passes(self, job_filter):
        job = {"title": "Head of Platform Engineering", "location": "Abu Dhabi, UAE", "description": ""}
        result, reason = job_filter.passes(job)
        assert result is True

    def test_cto_uae_passes(self, job_filter):
        job = {"title": "CTO", "location": "UAE", "description": ""}
        result, reason = job_filter.passes(job)
        assert result is True

    def test_no_title_fails(self, job_filter):
        job = {"title": "", "location": "Dubai, UAE", "description": ""}
        result, reason = job_filter.passes(job)
        assert result is False
        assert "no title" in reason

    def test_none_title_fails(self, job_filter):
        job = {"title": None, "location": "Dubai, UAE", "description": ""}
        result, reason = job_filter.passes(job)
        assert result is False

    def test_israel_location_fails(self, job_filter):
        job = {"title": "Director of Engineering", "location": "Tel Aviv, Israel", "description": ""}
        result, reason = job_filter.passes(job)
        assert result is False
        assert "israel" in reason.lower() or "excluded" in reason.lower()

    def test_tel_aviv_fails(self, job_filter):
        job = {"title": "VP Engineering", "location": "Tel Aviv", "description": ""}
        result, reason = job_filter.passes(job)
        assert result is False

    def test_ic_role_engineer_fails(self, job_filter):
        job = {"title": "Senior Software Engineer", "location": "Dubai, UAE", "description": ""}
        result, reason = job_filter.passes(job)
        assert result is False
        assert "senior role" in reason.lower() or "not a senior" in reason.lower()

    def test_manager_fails(self, job_filter):
        job = {"title": "Engineering Manager", "location": "Dubai, UAE", "description": ""}
        result, reason = job_filter.passes(job)
        assert result is False

    def test_london_fails(self, job_filter):
        job = {"title": "Director of Engineering", "location": "London, UK", "description": ""}
        result, reason = job_filter.passes(job)
        assert result is False
        assert "location" in reason.lower()

    def test_us_location_fails(self, job_filter):
        job = {"title": "Director of Engineering", "location": "San Francisco, CA", "description": ""}
        result, reason = job_filter.passes(job)
        assert result is False

    def test_no_location_passes_if_senior(self, job_filter):
        """Job with empty location and senior title should pass (location unknown)."""
        job = {"title": "Director of Engineering", "location": "", "description": ""}
        result, reason = job_filter.passes(job)
        assert result is True

    def test_combined_all_passing(self, job_filter):
        job = {
            "title": "Senior Director of Engineering",
            "location": "Dubai, UAE",
            "description": "Great role in Dubai.",
        }
        result, _ = job_filter.passes(job)
        assert result is True

    def test_combined_one_failing(self, job_filter):
        job = {
            "title": "Director of Engineering",
            "location": "London, UK",  # fails
            "description": "Role in London.",
        }
        result, _ = job_filter.passes(job)
        assert result is False

    def test_location_in_description_helps(self, job_filter):
        """If location field is absent but description mentions Dubai, should pass."""
        job = {
            "title": "Director of Engineering",
            "location": "",
            "description": "We are hiring in Dubai, UAE for this senior role.",
        }
        result, reason = job_filter.passes(job)
        assert result is True

    def test_middle_east_location_passes(self, job_filter):
        job = {"title": "VP Engineering", "location": "Middle East", "description": ""}
        result, _ = job_filter.passes(job)
        assert result is True

    def test_qatar_passes(self, job_filter):
        job = {"title": "Head of Engineering", "location": "Doha, Qatar", "description": ""}
        result, _ = job_filter.passes(job)
        assert result is True

    def test_kuwait_passes(self, job_filter):
        job = {"title": "Director of Engineering", "location": "Kuwait City, Kuwait", "description": ""}
        result, _ = job_filter.passes(job)
        assert result is True


class TestIsSeniorRole:
    """Test _is_senior_role() method."""

    def test_director_is_senior(self, job_filter):
        assert job_filter._is_senior_role("director of engineering", "") is True

    def test_vp_is_senior(self, job_filter):
        assert job_filter._is_senior_role("vp engineering", "") is True

    def test_vice_president_is_senior(self, job_filter):
        assert job_filter._is_senior_role("vice president engineering", "") is True

    def test_cto_is_senior(self, job_filter):
        assert job_filter._is_senior_role("cto", "") is True

    def test_head_of_is_senior(self, job_filter):
        assert job_filter._is_senior_role("head of platform engineering", "") is True

    def test_svp_is_senior(self, job_filter):
        assert job_filter._is_senior_role("svp engineering", "") is True

    def test_engineer_is_not_senior(self, job_filter):
        assert job_filter._is_senior_role("senior software engineer", "") is False

    def test_developer_is_not_senior(self, job_filter):
        assert job_filter._is_senior_role("senior developer", "") is False

    def test_manager_is_not_senior(self, job_filter):
        assert job_filter._is_senior_role("engineering manager", "") is False

    def test_architect_is_not_senior(self, job_filter):
        assert job_filter._is_senior_role("software architect", "") is False


class TestGetLocationScore:
    """Test get_location_score() method."""

    def test_dubai_scores_100(self, job_filter):
        assert job_filter.get_location_score("Dubai, UAE") == 100

    def test_abu_dhabi_scores_100(self, job_filter):
        assert job_filter.get_location_score("Abu Dhabi, UAE") == 100

    def test_riyadh_scores_100(self, job_filter):
        assert job_filter.get_location_score("Riyadh, Saudi Arabia") == 100

    def test_uae_scores_80(self, job_filter):
        assert job_filter.get_location_score("UAE") == 80

    def test_saudi_arabia_scores_80(self, job_filter):
        assert job_filter.get_location_score("Saudi Arabia") == 80

    def test_middle_east_scores_60(self, job_filter):
        assert job_filter.get_location_score("Middle East") == 60

    def test_qatar_scores_60(self, job_filter):
        assert job_filter.get_location_score("Doha, Qatar") == 60

    def test_israel_scores_0(self, job_filter):
        assert job_filter.get_location_score("Tel Aviv, Israel") == 0

    def test_unknown_location_scores_20(self, job_filter):
        assert job_filter.get_location_score("Random City, Unknown Country") == 20

    def test_london_scores_20(self, job_filter):
        assert job_filter.get_location_score("London, UK") == 20


class TestEstimateSeniorityScore:
    """Test estimate_seniority_score() method."""

    def test_cto_scores_95(self, job_filter):
        assert job_filter.estimate_seniority_score("CTO") == 95

    def test_vp_scores_90(self, job_filter):
        assert job_filter.estimate_seniority_score("VP of Engineering") == 90

    def test_director_scores_85(self, job_filter):
        assert job_filter.estimate_seniority_score("Director of Engineering") == 85

    def test_manager_scores_50(self, job_filter):
        assert job_filter.estimate_seniority_score("Engineering Manager") == 50

    def test_engineer_scores_30(self, job_filter):
        assert job_filter.estimate_seniority_score("Software Engineer") == 30

    def test_head_of_scores_85(self, job_filter):
        assert job_filter.estimate_seniority_score("Head of Engineering") == 85

    def test_chief_scores_95(self, job_filter):
        assert job_filter.estimate_seniority_score("Chief Technology Officer") == 95
