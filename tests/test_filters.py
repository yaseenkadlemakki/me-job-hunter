"""Tests for pre-scoring job filters."""

import pytest
from src.matching.filters import JobFilter, LOCATION_TIER


@pytest.fixture
def config():
    return {
        "filters": {
            "target_locations": ["Dubai", "Abu Dhabi", "Riyadh", "Saudi Arabia", "UAE", "Middle East"],
            "target_titles": [
                "Director", "Senior Director", "VP Engineering",
                "Head of Engineering", "Head of Platform", "CTO"
            ],
            "excluded_locations": ["Israel", "Tel Aviv"],
            "excluded_regions": ["IL"],
        }
    }


@pytest.fixture
def job_filter(config):
    return JobFilter(config=config)


# ===== Location Tests =====

def test_passes_dubai_director(job_filter):
    job = {"title": "Director of Engineering", "location": "Dubai, UAE", "description": ""}
    passes, reason = job_filter.passes(job)
    assert passes, f"Expected to pass, got: {reason}"


def test_passes_riyadh_vp(job_filter):
    job = {"title": "VP of Engineering", "location": "Riyadh, Saudi Arabia", "description": ""}
    passes, reason = job_filter.passes(job)
    assert passes, f"Expected to pass, got: {reason}"


def test_passes_head_of_platform(job_filter):
    job = {"title": "Head of Platform Engineering", "location": "Abu Dhabi, UAE", "description": ""}
    passes, reason = job_filter.passes(job)
    assert passes, f"Expected to pass, got: {reason}"


def test_passes_cto(job_filter):
    job = {"title": "CTO", "location": "Dubai", "description": ""}
    passes, reason = job_filter.passes(job)
    assert passes, f"Expected to pass, got: {reason}"


# ===== Exclusion Tests =====

def test_excludes_israel_location(job_filter):
    job = {"title": "Director of Engineering", "location": "Tel Aviv, Israel", "description": ""}
    passes, reason = job_filter.passes(job)
    assert not passes
    assert "excluded" in reason.lower()


def test_excludes_israel_by_name(job_filter):
    job = {"title": "Director of Engineering", "location": "Israel", "description": ""}
    passes, reason = job_filter.passes(job)
    assert not passes


# ===== Seniority Tests =====

def test_filters_junior_engineer(job_filter):
    job = {"title": "Software Engineer", "location": "Dubai, UAE", "description": ""}
    passes, reason = job_filter.passes(job)
    assert not passes
    assert "not a senior role" in reason.lower()


def test_filters_senior_engineer(job_filter):
    job = {"title": "Senior Software Engineer", "location": "Dubai, UAE", "description": ""}
    passes, reason = job_filter.passes(job)
    assert not passes


def test_passes_engineering_manager(job_filter):
    """Engineering Manager is borderline — test that director-level passes."""
    job = {"title": "Director, Engineering", "location": "Dubai, UAE", "description": ""}
    passes, _ = job_filter.passes(job)
    assert passes


# ===== Location Score Tests =====

def test_location_score_dubai(job_filter):
    score = job_filter.get_location_score("Dubai, UAE")
    assert score == 100


def test_location_score_riyadh(job_filter):
    score = job_filter.get_location_score("Riyadh, Saudi Arabia")
    assert score == 100


def test_location_score_uae(job_filter):
    score = job_filter.get_location_score("UAE")
    assert score >= 80


def test_location_score_excluded(job_filter):
    score = job_filter.get_location_score("Tel Aviv, Israel")
    assert score == 0


def test_location_score_other_middle_east(job_filter):
    score = job_filter.get_location_score("Doha, Qatar")
    assert score >= 60


# ===== Seniority Score Tests =====

def test_seniority_score_director(job_filter):
    score = job_filter.estimate_seniority_score("Director of Engineering")
    assert score >= 85


def test_seniority_score_vp(job_filter):
    score = job_filter.estimate_seniority_score("VP of Engineering")
    assert score >= 90


def test_seniority_score_cto(job_filter):
    score = job_filter.estimate_seniority_score("CTO")
    assert score >= 95


def test_seniority_score_head(job_filter):
    score = job_filter.estimate_seniority_score("Head of Platform Engineering")
    assert score >= 85


def test_seniority_score_engineer(job_filter):
    score = job_filter.estimate_seniority_score("Software Engineer")
    assert score <= 35


# ===== Edge Cases =====

def test_no_title(job_filter):
    job = {"title": "", "location": "Dubai, UAE", "description": ""}
    passes, reason = job_filter.passes(job)
    assert not passes
    assert "no title" in reason.lower()


def test_location_in_description(job_filter):
    """If location field is empty, check description."""
    job = {
        "title": "Director of Engineering",
        "location": "",
        "description": "This is a role based in Dubai, UAE for a leading tech company."
    }
    passes, reason = job_filter.passes(job)
    assert passes, f"Expected to pass (location in description), got: {reason}"
