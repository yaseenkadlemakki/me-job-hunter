"""Factory Boy factories for generating test data."""

from __future__ import annotations

import factory
import factory.fuzzy
from datetime import datetime, timedelta
import random


class JobFactory(factory.DictFactory):
    """Generate a random valid job dict."""
    source = factory.fuzzy.FuzzyChoice(["linkedin", "indeed", "bayt", "gulftarget", "naukrigulf"])
    title = factory.fuzzy.FuzzyChoice([
        "Director of Engineering",
        "VP of Engineering",
        "Head of Platform Engineering",
        "Head of Infrastructure",
        "Senior Director of Engineering",
        "CTO",
        "Head of DevOps",
    ])
    company = factory.fuzzy.FuzzyChoice([
        "Acme Cloud Inc",
        "Gulf Tech Corp",
        "Dubai Digital",
        "Emirates Software",
        "Riyadh Tech Hub",
        "Middle East Innovations",
    ])
    location = factory.fuzzy.FuzzyChoice([
        "Dubai, UAE",
        "Abu Dhabi, UAE",
        "Riyadh, Saudi Arabia",
        "Dubai Internet City, UAE",
    ])
    url = factory.LazyAttributeSequence(
        lambda obj, n: f"https://{obj.source}.com/jobs/view/{obj.title.lower().replace(' ', '-')}-{n}"
    )
    description = factory.LazyAttribute(lambda obj: (
        f"We are seeking a {obj.title} to lead our engineering team in {obj.location}. "
        f"Requirements: Kubernetes, AWS, DevOps, CI/CD, Team leadership. "
        f"Great compensation and benefits package."
    ))
    salary_raw = factory.fuzzy.FuzzyChoice([
        "AED 1,200,000 - 1,500,000",
        "AED 1,000,000 - 1,400,000",
        "AED 900,000 - 1,200,000",
        None,
    ])
    salary_estimated_aed = factory.LazyAttribute(
        lambda obj: 1250000.0 if obj.salary_raw else None
    )
    posted_date = factory.LazyFunction(
        lambda: datetime.utcnow() - timedelta(days=random.randint(0, 7))
    )
    seniority_level = "director"


class ScoredJobFactory(factory.DictFactory):
    """Generate a scored job dict."""
    skill_overlap = factory.fuzzy.FuzzyFloat(50, 100)
    seniority_alignment = factory.fuzzy.FuzzyFloat(50, 100)
    industry_alignment = factory.fuzzy.FuzzyFloat(50, 100)
    compensation_confidence = factory.fuzzy.FuzzyFloat(50, 100)
    location_relevance = factory.fuzzy.FuzzyFloat(50, 100)
    explanation = "Strong match for senior engineering role in Middle East."
    positioning_strategy = "Highlight platform scale and leadership depth."
    final_score = factory.fuzzy.FuzzyFloat(60, 95)


class DirectorDubaiJobFactory(JobFactory):
    """High-scoring job preset: Director-level in Dubai."""
    title = "Director of Engineering"
    company = "Acme Cloud Dubai"
    location = "Dubai, UAE"
    url = factory.LazyAttributeSequence(
        lambda obj, n: f"https://linkedin.com/jobs/view/director-dubai-{n}"
    )
    description = (
        "Director of Engineering for cloud platform team in Dubai. "
        "Requires: Kubernetes, AWS, DevOps, Platform Engineering, AI/ML. "
        "Lead 50+ engineers. Compensation: AED 1,400,000/year."
    )
    salary_raw = "AED 1,200,000 - 1,500,000"
    salary_estimated_aed = 1350000.0
    seniority_level = "director"


class ICRoleJobFactory(JobFactory):
    """Filtered-out job preset: IC role in non-target location."""
    title = "Senior Software Engineer"
    company = "Random Corp"
    location = "London, UK"
    url = factory.LazyAttributeSequence(
        lambda obj, n: f"https://indeed.com/jobs/senior-engineer-london-{n}"
    )
    description = "Senior Software Engineer for backend services. Python, Go, REST APIs."
    salary_raw = None
    salary_estimated_aed = None
    seniority_level = "ic"


class IsraelJobFactory(JobFactory):
    """Excluded job: Israel location."""
    title = "VP of Engineering"
    company = "Tel Aviv Tech"
    location = "Tel Aviv, Israel"
    url = factory.LazyAttributeSequence(
        lambda obj, n: f"https://linkedin.com/jobs/vp-engineering-israel-{n}"
    )
    description = "VP of Engineering for fast-growing startup in Tel Aviv."
    salary_raw = None
    salary_estimated_aed = None
    seniority_level = "vp"


class RawJobFactory(factory.DictFactory):
    """Raw job as returned by connectors (before parsing)."""
    source = "linkedin"
    title = "Director of Engineering"
    company = "Gulf Cloud Corp"
    location = "Dubai, UAE"
    url = factory.LazyAttributeSequence(
        lambda obj, n: f"https://linkedin.com/jobs/view/raw-{n}"
    )
    description = "<p>Director of Engineering role. <strong>Kubernetes</strong>, AWS required.</p>"
    salary_raw = "AED 1,200,000 - 1,500,000"
    posted_date = "2 days ago"
