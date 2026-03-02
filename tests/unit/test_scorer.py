"""Unit tests for src/matching/scorer.py"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.matching.scorer import Scorer, DEFAULT_WEIGHTS


@pytest.fixture
def scorer(config, mock_claude_client):
    """Scorer with mocked Anthropic client."""
    with patch("src.matching.scorer.anthropic.Anthropic", return_value=mock_claude_client):
        s = Scorer(config=config)
    return s


@pytest.fixture
def scorer_default(mock_claude_client):
    """Scorer with default config."""
    with patch("src.matching.scorer.anthropic.Anthropic", return_value=mock_claude_client):
        s = Scorer()
    return s


class TestWeights:
    """Test scoring weight configuration."""

    def test_default_weights_sum_to_one(self):
        total = sum(DEFAULT_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_default_skill_weight(self):
        assert DEFAULT_WEIGHTS["skill_overlap"] == 0.30

    def test_default_seniority_weight(self):
        assert DEFAULT_WEIGHTS["seniority_alignment"] == 0.25

    def test_default_industry_weight(self):
        assert DEFAULT_WEIGHTS["industry_alignment"] == 0.15

    def test_default_comp_weight(self):
        assert DEFAULT_WEIGHTS["compensation_confidence"] == 0.15

    def test_default_location_weight(self):
        assert DEFAULT_WEIGHTS["location_relevance"] == 0.15

    def test_config_weights_loaded(self, config):
        with patch("src.matching.scorer.anthropic.Anthropic"):
            scorer = Scorer(config=config)
        assert scorer.weights["skill_overlap"] == 0.30


class TestScore:
    """Test the async score() method."""

    @pytest.mark.asyncio
    async def test_returns_dict(self, scorer, sample_job_director_dubai, candidate_profile):
        result = await scorer.score(sample_job_director_dubai, candidate_profile)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_returns_final_score(self, scorer, sample_job_director_dubai, candidate_profile):
        result = await scorer.score(sample_job_director_dubai, candidate_profile)
        assert "final_score" in result

    @pytest.mark.asyncio
    async def test_score_range_0_to_100(self, scorer, sample_job_director_dubai, candidate_profile):
        result = await scorer.score(sample_job_director_dubai, candidate_profile)
        assert 0 <= result["final_score"] <= 100

    @pytest.mark.asyncio
    async def test_high_scoring_job_scores_high(
        self, config, candidate_profile, sample_job_director_dubai
    ):
        """Director-level role in Dubai should score >= 80."""
        high_score_json = json.dumps({
            "skill_overlap": 90,
            "seniority_alignment": 95,
            "industry_alignment": 80,
            "compensation_confidence": 85,
            "location_relevance": 100,
            "explanation": "Perfect match for Director role in Dubai.",
            "positioning_strategy": "Emphasize scale of Juniper platform team.",
        })
        mock_content = MagicMock()
        mock_content.text = high_score_json
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("src.matching.scorer.anthropic.Anthropic", return_value=mock_client):
            scorer = Scorer(config=config)
        result = await scorer.score(sample_job_director_dubai, candidate_profile)
        assert result["final_score"] >= 80

    @pytest.mark.asyncio
    async def test_ic_role_scores_low(
        self, config, candidate_profile, sample_job_ic_israel
    ):
        """IC role should score < 50."""
        low_score_json = json.dumps({
            "skill_overlap": 30,
            "seniority_alignment": 20,
            "industry_alignment": 30,
            "compensation_confidence": 20,
            "location_relevance": 0,
            "explanation": "Poor match: IC role in Israel.",
            "positioning_strategy": "Not recommended.",
        })
        mock_content = MagicMock()
        mock_content.text = low_score_json
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("src.matching.scorer.anthropic.Anthropic", return_value=mock_client):
            scorer = Scorer(config=config)
        result = await scorer.score(sample_job_ic_israel, candidate_profile)
        assert result["final_score"] < 50

    @pytest.mark.asyncio
    async def test_israel_location_relevance_zero(
        self, config, candidate_profile, sample_job_ic_israel
    ):
        """Israel job should have location_relevance = 0."""
        response_json = json.dumps({
            "skill_overlap": 50,
            "seniority_alignment": 50,
            "industry_alignment": 50,
            "compensation_confidence": 50,
            "location_relevance": 0,
            "explanation": "Israel is excluded.",
            "positioning_strategy": "Skip.",
        })
        mock_content = MagicMock()
        mock_content.text = response_json
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("src.matching.scorer.anthropic.Anthropic", return_value=mock_client):
            scorer = Scorer(config=config)
        result = await scorer.score(sample_job_ic_israel, candidate_profile)
        assert result["location_relevance"] == 0

    @pytest.mark.asyncio
    async def test_returns_explanation(self, scorer, sample_job_director_dubai, candidate_profile):
        result = await scorer.score(sample_job_director_dubai, candidate_profile)
        assert "explanation" in result
        assert isinstance(result["explanation"], str)

    @pytest.mark.asyncio
    async def test_returns_positioning_strategy(self, scorer, sample_job_director_dubai, candidate_profile):
        result = await scorer.score(sample_job_director_dubai, candidate_profile)
        assert "positioning_strategy" in result
        assert isinstance(result["positioning_strategy"], str)

    @pytest.mark.asyncio
    async def test_returns_default_on_parse_failure(
        self, config, candidate_profile, sample_job_director_dubai
    ):
        """Returns default score when Claude response cannot be parsed."""
        mock_content = MagicMock()
        mock_content.text = "not valid json at all %%%"
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("src.matching.scorer.anthropic.Anthropic", return_value=mock_client):
            scorer = Scorer(config=config)
        result = await scorer.score(sample_job_director_dubai, candidate_profile)
        assert result["final_score"] == 50.0

    @pytest.mark.asyncio
    async def test_raises_on_api_error_after_retries(
        self, config, candidate_profile, sample_job_director_dubai
    ):
        """Raises exception after all retry attempts exhausted."""
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API error")

        with patch("src.matching.scorer.anthropic.Anthropic", return_value=mock_client):
            # Disable retry for speed
            with patch("src.matching.scorer.retry", lambda **kwargs: lambda f: f):
                scorer = Scorer(config=config)
        with pytest.raises(Exception):
            await scorer.score(sample_job_director_dubai, candidate_profile)


class TestBuildPrompt:
    """Test _build_prompt() method."""

    def test_prompt_contains_candidate_name(self, scorer, sample_job_director_dubai, candidate_profile):
        prompt = scorer._build_prompt(sample_job_director_dubai, candidate_profile)
        assert candidate_profile["name"] in prompt

    def test_prompt_contains_job_title(self, scorer, sample_job_director_dubai, candidate_profile):
        prompt = scorer._build_prompt(sample_job_director_dubai, candidate_profile)
        assert sample_job_director_dubai["title"] in prompt

    def test_prompt_contains_company(self, scorer, sample_job_director_dubai, candidate_profile):
        prompt = scorer._build_prompt(sample_job_director_dubai, candidate_profile)
        assert sample_job_director_dubai["company"] in prompt

    def test_prompt_contains_location(self, scorer, sample_job_director_dubai, candidate_profile):
        prompt = scorer._build_prompt(sample_job_director_dubai, candidate_profile)
        assert sample_job_director_dubai["location"] in prompt

    def test_prompt_contains_skills(self, scorer, sample_job_director_dubai, candidate_profile):
        prompt = scorer._build_prompt(sample_job_director_dubai, candidate_profile)
        assert "Kubernetes" in prompt or "AWS" in prompt

    def test_prompt_truncates_description(self, scorer, candidate_profile):
        long_desc = "x" * 5000
        job = {"title": "D", "company": "C", "location": "Dubai", "description": long_desc}
        prompt = scorer._build_prompt(job, candidate_profile)
        # Description is capped at 3000 chars in scorer
        desc_section = prompt.split("Description:")[-1] if "Description:" in prompt else ""
        assert len(desc_section) < 4000


class TestParseResponse:
    """Test _parse_response() method."""

    def test_parses_valid_json(self, scorer):
        json_str = '{"skill_overlap": 80, "seniority_alignment": 90}'
        result = scorer._parse_response(json_str)
        assert result["skill_overlap"] == 80

    def test_parses_json_with_surrounding_text(self, scorer):
        content = 'Here is my response: {"skill_overlap": 80, "seniority_alignment": 90} done.'
        result = scorer._parse_response(content)
        assert result is not None
        assert result["skill_overlap"] == 80

    def test_returns_none_for_invalid_json(self, scorer):
        result = scorer._parse_response("not json at all %%%")
        assert result is None

    def test_parses_multiline_json(self, scorer):
        content = """{
  "skill_overlap": 85,
  "seniority_alignment": 90,
  "explanation": "Good match"
}"""
        result = scorer._parse_response(content)
        assert result is not None
        assert result["skill_overlap"] == 85


class TestCalculateFinalScore:
    """Test _calculate_final_score() method."""

    def test_calculates_weighted_sum(self, scorer):
        scores = {
            "skill_overlap": 100,
            "seniority_alignment": 100,
            "industry_alignment": 100,
            "compensation_confidence": 100,
            "location_relevance": 100,
        }
        result = scorer._calculate_final_score(scores)
        assert abs(result - 100.0) < 0.01

    def test_zero_scores_give_zero(self, scorer):
        scores = {
            "skill_overlap": 0,
            "seniority_alignment": 0,
            "industry_alignment": 0,
            "compensation_confidence": 0,
            "location_relevance": 0,
        }
        result = scorer._calculate_final_score(scores)
        assert result == 0.0

    def test_uses_defaults_for_missing_dimensions(self, scorer):
        # Missing keys default to 50
        scores = {"skill_overlap": 80}
        result = scorer._calculate_final_score(scores)
        # 80*0.30 + 50*0.25 + 50*0.15 + 50*0.15 + 50*0.15 = 24 + 12.5 + 7.5 + 7.5 + 7.5 = 59
        assert 55 <= result <= 65


class TestDefaultScore:
    """Test _default_score() method."""

    def test_default_score_keys(self, scorer):
        d = scorer._default_score()
        assert "skill_overlap" in d
        assert "seniority_alignment" in d
        assert "final_score" in d
        assert "explanation" in d
        assert "positioning_strategy" in d

    def test_default_final_score_is_50(self, scorer):
        d = scorer._default_score()
        assert d["final_score"] == 50.0


class TestPassesFilter:
    """Test passes_filter() method."""

    def test_high_score_passes(self, scorer):
        score = {"final_score": 85.0}
        assert scorer.passes_filter(score, min_score=80.0) is True

    def test_exact_threshold_passes(self, scorer):
        score = {"final_score": 80.0}
        assert scorer.passes_filter(score, min_score=80.0) is True

    def test_below_threshold_fails(self, scorer):
        score = {"final_score": 75.0}
        assert scorer.passes_filter(score, min_score=80.0) is False

    def test_zero_score_fails(self, scorer):
        score = {"final_score": 0}
        assert scorer.passes_filter(score) is False

    def test_missing_final_score_fails(self, scorer):
        assert scorer.passes_filter({}) is False


class TestEstimateSalary:
    """Test estimate_salary_aed() method."""

    @pytest.mark.asyncio
    async def test_returns_float_on_success(self, config, candidate_profile):
        salary_json = '{"estimated_aed": 1400000, "confidence": "high", "reasoning": "Director role in UAE"}'
        mock_content = MagicMock()
        mock_content.text = salary_json
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("src.matching.scorer.anthropic.Anthropic", return_value=mock_client):
            scorer = Scorer(config=config)
        result = await scorer.estimate_salary_aed({"title": "Director", "company": "C", "location": "Dubai"})
        assert result == 1400000.0

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self, config):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API error")

        with patch("src.matching.scorer.anthropic.Anthropic", return_value=mock_client):
            scorer = Scorer(config=config)
        result = await scorer.estimate_salary_aed({"title": "D", "company": "C", "location": "Dubai"})
        assert result is None
