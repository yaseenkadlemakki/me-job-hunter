"""Parse resume.pdf into a structured candidate profile."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from src.utils.logger import setup_logger

logger = setup_logger("resume_parser")

# Hardcoded profile for Yaseen Kadlemakki (parsed from resume.pdf)
# This is the authoritative source of truth for the candidate profile.
CANDIDATE_PROFILE = {
    "name": "Yaseen Kadlemakki",
    "email": "yaseenkadlemakki@gmail.com",
    "linkedin": "https://www.linkedin.com/in/yaseenkadlemakki/",
    "current_role": "Director of Engineering",
    "current_company": "Juniper Networks",
    "location": "Greater Boston, MA",
    "target_location": "Middle East (UAE, Saudi Arabia)",
    "current_comp_usd": 600000,
    "target_comp_aed": 1200000,
    "years_experience": 15,
    "team_size": 75,
    "skills": [
        "Cloud Architecture (AWS)",
        "Kubernetes",
        "DevOps",
        "SRE",
        "Platform Engineering",
        "AI/ML",
        "MLOps",
        "CrewAI",
        "Agentic Development",
        "CI/CD",
        "Terraform",
        "Infrastructure as Code",
        "Developer Productivity",
        "Networking",
        "Datacenter",
        "Python",
        "Go",
        "Microservices",
        "Service Mesh",
        "Observability",
        "OpenTelemetry",
        "FinOps",
        "GitOps",
        "ArgoCD",
        "Helm",
        "Docker",
        "Linux",
        "Security",
        "Multi-cloud",
        "Engineering Leadership",
        "Team Building",
        "Strategic Planning",
        "OKRs",
        "Agile/Scrum",
        "Stakeholder Management",
        "P&L Management",
        "Vendor Management",
        "Recruiting",
        "Mentoring",
    ],
    "industries": [
        "Enterprise SaaS",
        "Networking",
        "Cloud Infrastructure",
        "Datacenter",
        "Telecommunications",
        "Software Development",
    ],
    "education": [
        {
            "degree": "MBA",
            "institution": "University of New Hampshire",
            "field": "Business Administration",
        },
        {
            "degree": "B.E.",
            "institution": "Visvesvaraya Technological University",
            "field": "Engineering",
        },
    ],
    "target_roles": [
        "Director of Engineering",
        "Senior Director of Engineering",
        "VP of Engineering",
        "Vice President of Engineering",
        "Head of Engineering",
        "Head of Platform Engineering",
        "Head of Infrastructure",
        "Head of DevOps",
        "Head of Networking",
        "CTO",
        "Chief Technology Officer",
        "Engineering Director",
    ],
    "key_achievements": [
        "Led 75+ engineers across multi-geo teams with Senior Managers reporting in",
        "Built and scaled platform engineering organization at Juniper Networks",
        "Drove AI/ML and MLOps adoption across engineering teams",
        "Implemented enterprise-scale Kubernetes and cloud infrastructure",
        "Reduced infrastructure costs through FinOps practices",
        "Built developer productivity platforms used by 500+ engineers",
    ],
    "languages": ["English (fluent)", "Hindi (native)", "Kannada (native)"],
    "certifications": [],
    "summary": (
        "Seasoned engineering executive with 15+ years building and scaling high-performance "
        "engineering organizations. Currently Director of Engineering at Juniper Networks leading "
        "75+ engineers across platform, infrastructure, DevOps, and AI/ML domains. Proven track "
        "record of delivering enterprise-scale cloud infrastructure, developer productivity platforms, "
        "and cutting-edge AI/ML systems. Seeking senior executive role (Director, VP, Head of Engineering) "
        "in UAE/Saudi Arabia with compensation of 1.2M+ AED."
    ),
}


class ResumeParser:
    """Parse resume PDF into structured profile. Falls back to hardcoded profile."""

    def __init__(self, resume_path: str = "resume.pdf"):
        self.resume_path = Path(resume_path)

    def parse(self) -> dict:
        """Return structured candidate profile."""
        if self.resume_path.exists():
            try:
                extracted = self._extract_from_pdf()
                if extracted:
                    logger.info(f"Parsed resume from {self.resume_path}")
                    return self._merge_with_defaults(extracted)
            except Exception as e:
                logger.warning(f"PDF parsing failed, using hardcoded profile: {e}")
        else:
            logger.info("resume.pdf not found, using hardcoded candidate profile")

        return CANDIDATE_PROFILE.copy()

    def _extract_from_pdf(self) -> Optional[dict]:
        """Extract text from PDF and return basic structure."""
        try:
            import pdfplumber
            text_blocks = []
            with pdfplumber.open(str(self.resume_path)) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        text_blocks.append(text)
            full_text = "\n".join(text_blocks)
            if len(full_text) < 100:
                return None
            logger.debug(f"Extracted {len(full_text)} chars from resume PDF")
            return {"raw_text": full_text}
        except ImportError:
            try:
                import fitz  # pymupdf
                doc = fitz.open(str(self.resume_path))
                text_blocks = [page.get_text() for page in doc]
                full_text = "\n".join(text_blocks)
                return {"raw_text": full_text} if len(full_text) > 100 else None
            except Exception:
                return None

    def _merge_with_defaults(self, extracted: dict) -> dict:
        """Merge extracted data with hardcoded defaults (defaults win for structured fields)."""
        profile = CANDIDATE_PROFILE.copy()
        if "raw_text" in extracted:
            profile["resume_text"] = extracted["raw_text"]
        return profile

    def get_profile(self) -> dict:
        """Alias for parse()."""
        return self.parse()


def load_candidate_profile(resume_path: str = "resume.pdf", config: dict = None) -> dict:
    """Load candidate profile, optionally merging with config overrides."""
    parser = ResumeParser(resume_path)
    profile = parser.parse()

    if config and "candidate" in config:
        cfg = config["candidate"]
        # Config overrides for key fields
        for field in ["name", "email", "linkedin", "current_comp_usd", "target_comp_aed"]:
            if field in cfg:
                profile[field] = cfg[field]

    return profile
