"""Functional tests for the full scoring pipeline (filter → score → notify)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.matching.scorer import Scorer
from src.matching.filters import JobFilter


def make_claude_response(
    skill=80, seniority=85, industry=75, comp=80, location=100,
    explanation="Good match.", positioning="Emphasize scale."
):
    return json.dumps({
        "skill_overlap": skill,
        "seniority_alignment": seniority,
        "industry_alignment": industry,
        "compensation_confidence": comp,
        "location_relevance": location,
        "explanation": explanation,
        "positioning_strategy": positioning,
    })


@pytest.fixture
def scorer_with_mock(config):
    resp = make_claude_response()
    mock_content = MagicMock()
    mock_content.text = resp
    mock_response = MagicMock()
    mock_response.content = [mock_content]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("src.matching.scorer.anthropic.Anthropic", return_value=mock_client):
        scorer = Scorer(config=config)
    scorer._mock_client = mock_client
    return scorer


class TestScoringPipeline:
    """End-to-end scoring pipeline tests."""

    @pytest.mark.asyncio
    async def test_strong_match_scores_high(self, config, candidate_profile, sample_job_director_dubai):
        """Profile + strong matching Director in Dubai job → score >= 80."""
        resp = make_claude_response(
            skill=90, seniority=95, industry=80, comp=85, location=100,
            explanation="Strong match.", positioning="Lead with platform scale."
        )
        mock_content = MagicMock()
        mock_content.text = resp
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("src.matching.scorer.anthropic.Anthropic", return_value=mock_client):
            scorer = Scorer(config=config)
        result = await scorer.score(sample_job_director_dubai, candidate_profile)
        assert result["final_score"] >= 80

    @pytest.mark.asyncio
    async def test_weak_match_scores_low(self, config, candidate_profile, sample_job_ic_israel):
        """Profile + IC role in Israel → score < 50."""
        resp = make_claude_response(skill=30, seniority=20, industry=30, comp=20, location=0)
        mock_content = MagicMock()
        mock_content.text = resp
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("src.matching.scorer.anthropic.Anthropic", return_value=mock_client):
            scorer = Scorer(config=config)
        result = await scorer.score(sample_job_ic_israel, candidate_profile)
        assert result["final_score"] < 50

    def test_israel_job_filtered_before_scoring(self, config, sample_job_ic_israel):
        """Israel job should be filtered out before calling scorer."""
        job_filter = JobFilter(config=config)
        passes, reason = job_filter.passes(sample_job_ic_israel)
        assert passes is False
        assert "israel" in reason.lower() or "excluded" in reason.lower()

    def test_ic_role_filtered_before_scoring(self, config):
        """IC role should be filtered out before calling scorer."""
        job_filter = JobFilter(config=config)
        job = {"title": "Senior Software Engineer", "location": "Dubai", "description": ""}
        passes, reason = job_filter.passes(job)
        assert passes is False

    @pytest.mark.asyncio
    async def test_score_components_sum_correctly(self, config, candidate_profile, sample_job_director_dubai):
        """Score components should match the weighted sum."""
        skill, seniority, industry, comp, location = 80, 90, 70, 75, 100
        resp = make_claude_response(
            skill=skill, seniority=seniority, industry=industry, comp=comp, location=location
        )
        mock_content = MagicMock()
        mock_content.text = resp
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("src.matching.scorer.anthropic.Anthropic", return_value=mock_client):
            scorer = Scorer(config=config)

        result = await scorer.score(sample_job_director_dubai, candidate_profile)

        expected = (
            skill * 0.30 +
            seniority * 0.25 +
            industry * 0.15 +
            comp * 0.15 +
            location * 0.15
        )
        assert abs(result["final_score"] - expected) < 0.01

    @pytest.mark.asyncio
    async def test_positioning_strategy_non_empty_for_high_score(
        self, config, candidate_profile, sample_job_director_dubai
    ):
        resp = make_claude_response(
            skill=90, seniority=95, industry=85, comp=85, location=100,
            positioning="Lead with Juniper scale and Dubai market knowledge."
        )
        mock_content = MagicMock()
        mock_content.text = resp
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("src.matching.scorer.anthropic.Anthropic", return_value=mock_client):
            scorer = Scorer(config=config)
        result = await scorer.score(sample_job_director_dubai, candidate_profile)
        assert result["positioning_strategy"]  # non-empty

    @pytest.mark.asyncio
    async def test_explanation_references_skills(
        self, config, candidate_profile, sample_job_director_dubai
    ):
        resp = make_claude_response(
            explanation="Strong match: AWS and Kubernetes skills align perfectly with requirements."
        )
        mock_content = MagicMock()
        mock_content.text = resp
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("src.matching.scorer.anthropic.Anthropic", return_value=mock_client):
            scorer = Scorer(config=config)
        result = await scorer.score(sample_job_director_dubai, candidate_profile)
        assert "AWS" in result["explanation"] or "Kubernetes" in result["explanation"]

    def test_director_dubai_passes_filter(self, config, sample_job_director_dubai):
        """Director role in Dubai should pass all pre-scoring filters."""
        job_filter = JobFilter(config=config)
        passes, reason = job_filter.passes(sample_job_director_dubai)
        assert passes is True

    def test_no_salary_job_passes_filter(self, config, sample_job_no_salary):
        """Job with no salary should still pass filter (salary is not a filter criterion)."""
        job_filter = JobFilter(config=config)
        passes, _ = job_filter.passes(sample_job_no_salary)
        assert passes is True
