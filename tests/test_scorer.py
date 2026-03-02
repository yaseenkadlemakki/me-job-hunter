"""Tests for the job scoring engine."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.matching.scorer import Scorer, DEFAULT_WEIGHTS


@pytest.fixture
def config():
    return {
        "scoring_weights": DEFAULT_WEIGHTS,
        "llm": {
            "scoring_model": "claude-3-5-haiku-20241022",
            "max_tokens": 2048,
            "temperature": 0.1,
        },
    }


@pytest.fixture
def candidate_profile():
    return {
        "name": "Yaseen Kadlemakki",
        "current_role": "Director of Engineering",
        "current_company": "Juniper Networks",
        "years_experience": 15,
        "team_size": 75,
        "skills": ["Kubernetes", "AWS", "DevOps", "Platform Engineering", "AI/ML"],
        "industries": ["Enterprise SaaS", "Networking", "Cloud Infrastructure"],
        "target_comp_aed": 1200000,
    }


@pytest.fixture
def sample_job():
    return {
        "title": "Director of Engineering",
        "company": "ACME Cloud",
        "location": "Dubai, UAE",
        "url": "https://example.com/jobs/123",
        "description": "We are looking for a Director of Engineering to lead our platform team...",
        "salary_raw": "AED 1,500,000 - 2,000,000",
        "source": "linkedin",
    }


@pytest.fixture
def mock_claude_response():
    return json.dumps({
        "skill_overlap": 90,
        "seniority_alignment": 95,
        "industry_alignment": 85,
        "compensation_confidence": 92,
        "location_relevance": 98,
        "explanation": "Excellent match — all key skills aligned, Dubai location, comp above target.",
        "positioning_strategy": "Emphasize platform engineering leadership and AI/ML expertise.",
    })


def test_scorer_init(config):
    with patch("anthropic.Anthropic"):
        scorer = Scorer(config=config)
        assert scorer.weights == DEFAULT_WEIGHTS
        assert scorer.model == "claude-3-5-haiku-20241022"


def test_calculate_final_score(config):
    with patch("anthropic.Anthropic"):
        scorer = Scorer(config=config)
        scores = {
            "skill_overlap": 90,
            "seniority_alignment": 95,
            "industry_alignment": 85,
            "compensation_confidence": 92,
            "location_relevance": 98,
        }
        final = scorer._calculate_final_score(scores)
        # Verify weighted calculation
        expected = (
            90 * 0.30 +
            95 * 0.25 +
            85 * 0.15 +
            92 * 0.15 +
            98 * 0.15
        )
        assert abs(final - expected) < 0.01


def test_parse_response_valid_json(config):
    with patch("anthropic.Anthropic"):
        scorer = Scorer(config=config)
        response = '{"skill_overlap": 85, "seniority_alignment": 90, "industry_alignment": 80, "compensation_confidence": 75, "location_relevance": 95, "explanation": "test", "positioning_strategy": "test"}'
        result = scorer._parse_response(response)
        assert result is not None
        assert result["skill_overlap"] == 85


def test_parse_response_json_in_text(config):
    with patch("anthropic.Anthropic"):
        scorer = Scorer(config=config)
        response = 'Here is the assessment:\n{"skill_overlap": 85, "seniority_alignment": 90, "industry_alignment": 80, "compensation_confidence": 75, "location_relevance": 95, "explanation": "test", "positioning_strategy": "test"}\nDone.'
        result = scorer._parse_response(response)
        assert result is not None
        assert result["skill_overlap"] == 85


def test_parse_response_invalid(config):
    with patch("anthropic.Anthropic"):
        scorer = Scorer(config=config)
        result = scorer._parse_response("not json at all")
        assert result is None


def test_default_score(config):
    with patch("anthropic.Anthropic"):
        scorer = Scorer(config=config)
        score = scorer._default_score()
        assert score["final_score"] == 50.0
        assert "explanation" in score


def test_passes_filter_above_threshold(config):
    with patch("anthropic.Anthropic"):
        scorer = Scorer(config=config)
        score = {"final_score": 85.0}
        assert scorer.passes_filter(score, min_score=80.0) is True


def test_passes_filter_below_threshold(config):
    with patch("anthropic.Anthropic"):
        scorer = Scorer(config=config)
        score = {"final_score": 75.0}
        assert scorer.passes_filter(score, min_score=80.0) is False


@pytest.mark.asyncio
async def test_score_job(config, candidate_profile, sample_job, mock_claude_response):
    """Test full scoring pipeline with mocked Claude."""
    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=mock_claude_response)]
        mock_client.messages.create.return_value = mock_message

        scorer = Scorer(config=config)
        result = await scorer.score(sample_job, candidate_profile)

        assert "final_score" in result
        assert result["final_score"] > 80
        assert result["skill_overlap"] == 90
        assert result["location_relevance"] == 98


def test_build_prompt(config, candidate_profile, sample_job):
    with patch("anthropic.Anthropic"):
        scorer = Scorer(config=config)
        prompt = scorer._build_prompt(sample_job, candidate_profile)
        assert "Yaseen Kadlemakki" in prompt
        assert "Director of Engineering" in prompt
        assert "Dubai" in prompt
        assert "Kubernetes" in prompt
