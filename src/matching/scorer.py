"""Job relevance scoring engine using Claude claude-3-5-haiku-20241022."""

from __future__ import annotations

import json
import os
import re
from typing import Optional

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from src.utils.logger import setup_logger

logger = setup_logger("scorer")

DEFAULT_WEIGHTS = {
    "skill_overlap": 0.30,
    "seniority_alignment": 0.25,
    "industry_alignment": 0.15,
    "compensation_confidence": 0.15,
    "location_relevance": 0.15,
}

SCORING_PROMPT_TEMPLATE = """You are an expert executive recruiter evaluating job fit for a senior engineering leader.

## Candidate Profile
- **Name:** {name}
- **Current Role:** {current_role} at {current_company}
- **Years Experience:** {years_experience}+
- **Team Size Led:** {team_size}+ engineers
- **Skills:** {skills}
- **Industries:** {industries}
- **Target Comp:** {target_comp_aed} AED/year (equivalent to ~$330K+ USD)
- **Target Locations:** UAE (Dubai, Abu Dhabi), Saudi Arabia (Riyadh), Middle East
- **Target Roles:** Director, Senior Director, VP, Head of Engineering/Platform/Infrastructure/DevOps

## Job Posting
- **Title:** {title}
- **Company:** {company}
- **Location:** {location}
- **Salary:** {salary}
- **Description:**
{description}

## Task
Score this job's fit for the candidate on each dimension (0-100):

1. **skill_overlap** (0-100): How well do the required skills match the candidate's technical background?
   - 90-100: Perfect match, all key skills present
   - 70-89: Strong match, most skills align
   - 50-69: Moderate match, some relevant skills
   - 0-49: Poor match, few relevant skills

2. **seniority_alignment** (0-100): Is this role at the appropriate seniority level?
   - 90-100: Perfect level (Director/VP/Head)
   - 70-89: Close level (slight under/over)
   - 50-69: Manageable mismatch
   - 0-49: Significantly under or over level

3. **industry_alignment** (0-100): How relevant is the industry/domain?
   - 90-100: Same industry (networking, cloud, enterprise SaaS)
   - 70-89: Adjacent industry
   - 50-69: Transferable skills
   - 0-49: Very different domain

4. **compensation_confidence** (0-100): Likelihood this role meets the compensation target?
   - 90-100: Explicit salary at/above 1.2M AED
   - 70-89: Company/role size suggests strong comp
   - 50-69: Unclear but possible
   - 0-49: Likely below target or too small a company

5. **location_relevance** (0-100): How well does the location match?
   - 90-100: Dubai, Abu Dhabi, Riyadh (perfect target cities)
   - 70-89: UAE or Saudi Arabia (correct country)
   - 50-69: Other Middle East region
   - 0-49: Wrong region or excluded location

Respond with ONLY valid JSON (no markdown, no explanation outside JSON):
{{
  "skill_overlap": <0-100>,
  "seniority_alignment": <0-100>,
  "industry_alignment": <0-100>,
  "compensation_confidence": <0-100>,
  "location_relevance": <0-100>,
  "explanation": "<2-3 sentence summary of fit and gaps>",
  "positioning_strategy": "<1-2 sentence advice on how candidate should position themselves for this role>"
}}"""


class Scorer:
    """Score job relevance using Claude claude-3-5-haiku-20241022."""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.weights = {**DEFAULT_WEIGHTS, **self.config.get("scoring_weights", {})}
        llm_cfg = self.config.get("llm", {})
        self.model = llm_cfg.get("scoring_model", "claude-3-5-haiku-20241022")
        self.max_tokens = llm_cfg.get("max_tokens", 2048)
        self.temperature = llm_cfg.get("temperature", 0.1)
        self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def score(self, job_data: dict, candidate_profile: dict) -> dict:
        """Score a job against the candidate profile. Returns score dict."""
        prompt = self._build_prompt(job_data, candidate_profile)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                messages=[{"role": "user", "content": prompt}],
            )

            content = response.content[0].text.strip()
            scores = self._parse_response(content)

            if scores is None:
                logger.warning(f"Failed to parse score response for {job_data.get('title')}")
                return self._default_score()

            final = self._calculate_final_score(scores)
            scores["final_score"] = round(final, 1)

            logger.info(
                f"Scored: '{job_data.get('title')}' @ '{job_data.get('company')}' "
                f"→ {scores['final_score']}/100"
            )
            return scores

        except Exception as e:
            logger.error(f"Scoring failed for {job_data.get('url', 'unknown')}: {e}")
            raise

    def _build_prompt(self, job_data: dict, candidate: dict) -> str:
        desc = (job_data.get("description") or "")[:3000]
        skills = ", ".join(candidate.get("skills", [])[:20])

        return SCORING_PROMPT_TEMPLATE.format(
            name=candidate.get("name", "Candidate"),
            current_role=candidate.get("current_role", "Director of Engineering"),
            current_company=candidate.get("current_company", ""),
            years_experience=candidate.get("years_experience", 15),
            team_size=candidate.get("team_size", 75),
            skills=skills,
            industries=", ".join(candidate.get("industries", [])),
            target_comp_aed=candidate.get("target_comp_aed", 1200000),
            title=job_data.get("title", ""),
            company=job_data.get("company", ""),
            location=job_data.get("location", ""),
            salary=job_data.get("salary_raw") or "Not specified",
            description=desc,
        )

    def _parse_response(self, content: str) -> Optional[dict]:
        """Parse JSON from Claude response."""
        try:
            # Direct parse
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from text
        patterns = [
            r"\{[^{}]*\}",  # Simple JSON object
            r"\{[\s\S]*\}",  # Multiline JSON object
        ]
        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    continue

        logger.warning(f"Could not parse JSON from: {content[:200]}")
        return None

    def _calculate_final_score(self, scores: dict) -> float:
        """Calculate weighted final score."""
        total = 0.0
        for dimension, weight in self.weights.items():
            value = scores.get(dimension, 50)
            total += float(value) * weight
        return total

    def _default_score(self) -> dict:
        """Return a safe default score when API fails."""
        return {
            "skill_overlap": 50,
            "seniority_alignment": 50,
            "industry_alignment": 50,
            "compensation_confidence": 50,
            "location_relevance": 50,
            "explanation": "Scoring unavailable",
            "positioning_strategy": "Review manually",
            "final_score": 50.0,
        }

    def passes_filter(self, score: dict, min_score: float = 80.0) -> bool:
        """Check if a job score passes the minimum threshold."""
        return score.get("final_score", 0) >= min_score

    async def estimate_salary_aed(self, job_data: dict) -> Optional[float]:
        """Use Claude to estimate salary in AED when not listed."""
        prompt = (
            f"Estimate the annual salary in AED for this senior engineering role in the Middle East.\n\n"
            f"Role: {job_data.get('title', '')}\n"
            f"Company: {job_data.get('company', '')}\n"
            f"Location: {job_data.get('location', '')}\n\n"
            f"Respond with ONLY a JSON object: {{\"estimated_aed\": <number>, "
            f"\"confidence\": \"low|medium|high\", \"reasoning\": \"<brief explanation>\"}}"
        )
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=256,
                temperature=0.1,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.content[0].text.strip()
            data = self._parse_response(content)
            if data and "estimated_aed" in data:
                return float(data["estimated_aed"])
        except Exception as e:
            logger.debug(f"Salary estimation failed: {e}")
        return None
