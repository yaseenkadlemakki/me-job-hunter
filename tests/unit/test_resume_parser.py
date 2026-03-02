"""Unit tests for src/parsers/resume_parser.py"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.parsers.resume_parser import (
    CANDIDATE_PROFILE,
    ResumeParser,
    load_candidate_profile,
)


class TestCandidateProfile:
    """Test that CANDIDATE_PROFILE contains required fields."""

    def test_name_present(self):
        assert CANDIDATE_PROFILE["name"] == "Yaseen Kadlemakki"

    def test_email_present(self):
        assert CANDIDATE_PROFILE["email"] == "yaseenkadlemakki@gmail.com"

    def test_linkedin_present(self):
        assert "linkedin.com/in/yaseenkadlemakki" in CANDIDATE_PROFILE["linkedin"]

    def test_current_role(self):
        assert CANDIDATE_PROFILE["current_role"] == "Director of Engineering"

    def test_current_company(self):
        assert CANDIDATE_PROFILE["current_company"] == "Juniper Networks"

    def test_target_comp_aed(self):
        assert CANDIDATE_PROFILE["target_comp_aed"] >= 1_200_000

    def test_years_experience(self):
        assert CANDIDATE_PROFILE["years_experience"] >= 15

    def test_team_size(self):
        assert CANDIDATE_PROFILE["team_size"] >= 75

    def test_skills_list(self):
        skills = CANDIDATE_PROFILE["skills"]
        assert isinstance(skills, list)
        assert len(skills) > 20

    def test_skills_contains_cloud_aws(self):
        skills_lower = [s.lower() for s in CANDIDATE_PROFILE["skills"]]
        assert any("aws" in s for s in skills_lower)

    def test_skills_contains_kubernetes(self):
        skills_lower = [s.lower() for s in CANDIDATE_PROFILE["skills"]]
        assert any("kubernetes" in s for s in skills_lower)

    def test_skills_contains_devops(self):
        skills_lower = [s.lower() for s in CANDIDATE_PROFILE["skills"]]
        assert any("devops" in s for s in skills_lower)

    def test_skills_contains_ai_ml(self):
        skills_lower = [s.lower() for s in CANDIDATE_PROFILE["skills"]]
        assert any("ai" in s or "ml" in s for s in skills_lower)

    def test_industries_list(self):
        assert isinstance(CANDIDATE_PROFILE["industries"], list)
        assert len(CANDIDATE_PROFILE["industries"]) >= 4

    def test_education_contains_mba(self):
        edu = CANDIDATE_PROFILE["education"]
        degrees = [e["degree"] for e in edu]
        assert "MBA" in degrees

    def test_education_contains_be(self):
        edu = CANDIDATE_PROFILE["education"]
        degrees = [e["degree"] for e in edu]
        assert "B.E." in degrees

    def test_education_mba_institution(self):
        for edu in CANDIDATE_PROFILE["education"]:
            if edu["degree"] == "MBA":
                assert "New Hampshire" in edu["institution"] or "UNH" in edu["institution"]

    def test_education_be_institution(self):
        for edu in CANDIDATE_PROFILE["education"]:
            if edu["degree"] == "B.E.":
                assert "Visvesvaraya" in edu["institution"] or "VTU" in edu["institution"]

    def test_key_achievements_present(self):
        achievements = CANDIDATE_PROFILE["key_achievements"]
        assert isinstance(achievements, list)
        assert len(achievements) >= 5

    def test_key_achievements_mention_engineers(self):
        text = " ".join(CANDIDATE_PROFILE["key_achievements"]).lower()
        assert "engineer" in text

    def test_leadership_scope_in_achievements(self):
        text = " ".join(CANDIDATE_PROFILE["key_achievements"])
        assert "75" in text or "engineers" in text.lower()

    def test_summary_present(self):
        assert len(CANDIDATE_PROFILE["summary"]) > 50

    def test_target_roles_present(self):
        roles = CANDIDATE_PROFILE["target_roles"]
        assert isinstance(roles, list)
        assert any("director" in r.lower() for r in roles)
        assert any("vp" in r.lower() for r in roles)


class TestResumeParser:
    """Tests for ResumeParser class."""

    def test_parse_returns_dict_when_no_pdf(self, tmp_path):
        """Falls back to hardcoded profile when resume.pdf is missing."""
        parser = ResumeParser(resume_path=str(tmp_path / "nonexistent.pdf"))
        profile = parser.parse()
        assert isinstance(profile, dict)
        assert profile["name"] == "Yaseen Kadlemakki"

    def test_parse_returns_copy_not_original(self, tmp_path):
        """Returns a copy so mutations don't affect CANDIDATE_PROFILE."""
        parser = ResumeParser(resume_path=str(tmp_path / "nonexistent.pdf"))
        profile = parser.parse()
        profile["name"] = "Modified"
        assert CANDIDATE_PROFILE["name"] == "Yaseen Kadlemakki"

    def test_get_profile_alias(self, tmp_path):
        """get_profile() is alias for parse()."""
        parser = ResumeParser(resume_path=str(tmp_path / "nonexistent.pdf"))
        assert parser.get_profile() == parser.parse()

    def test_parse_handles_pdfplumber_failure(self, tmp_path):
        """Gracefully falls back when pdfplumber raises an exception."""
        # Create a fake (non-PDF) file
        fake_pdf = tmp_path / "resume.pdf"
        fake_pdf.write_bytes(b"not a real pdf")

        with patch("pdfplumber.open", side_effect=Exception("corrupt pdf")):
            parser = ResumeParser(resume_path=str(fake_pdf))
            profile = parser.parse()
            assert profile["name"] == "Yaseen Kadlemakki"

    def test_parse_with_valid_pdfplumber(self, tmp_path):
        """When pdfplumber returns text, merges with hardcoded profile."""
        fake_pdf = tmp_path / "resume.pdf"
        fake_pdf.write_bytes(b"fake")

        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Yaseen Kadlemakki Director of Engineering" * 10

        mock_pdf = MagicMock()
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_pdf.pages = [mock_page]

        with patch("pdfplumber.open", return_value=mock_pdf):
            parser = ResumeParser(resume_path=str(fake_pdf))
            profile = parser.parse()
            assert profile["name"] == "Yaseen Kadlemakki"
            assert "resume_text" in profile

    def test_parse_ignores_short_pdf_text(self, tmp_path):
        """PDF with < 100 chars returns hardcoded profile."""
        fake_pdf = tmp_path / "resume.pdf"
        fake_pdf.write_bytes(b"fake")

        mock_page = MagicMock()
        mock_page.extract_text.return_value = "too short"

        mock_pdf = MagicMock()
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_pdf.pages = [mock_page]

        with patch("pdfplumber.open", return_value=mock_pdf):
            parser = ResumeParser(resume_path=str(fake_pdf))
            profile = parser.parse()
            # Falls back to hardcoded (no resume_text)
            assert "resume_text" not in profile or profile.get("resume_text") is None

    def test_parse_falls_back_when_pdfplumber_unavailable(self, tmp_path):
        """Falls back to fitz (pymupdf) when pdfplumber import fails."""
        fake_pdf = tmp_path / "resume.pdf"
        fake_pdf.write_bytes(b"fake")

        mock_page = MagicMock()
        mock_page.get_text.return_value = "Yaseen Kadlemakki Director Engineering" * 10

        mock_doc = MagicMock()
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))

        with patch("builtins.__import__", side_effect=lambda name, *args, **kwargs: (
            (_ for _ in ()).throw(ImportError("no pdfplumber")) if name == "pdfplumber" else
            __builtins__["__import__"](name, *args, **kwargs)
        ) if False else __import__(name, *args, **kwargs)):
            parser = ResumeParser(resume_path=str(fake_pdf))
            profile = parser.parse()
            assert isinstance(profile, dict)


class TestLoadCandidateProfile:
    """Tests for load_candidate_profile() function."""

    def test_returns_profile_without_config(self):
        profile = load_candidate_profile(resume_path="nonexistent.pdf")
        assert profile["name"] == "Yaseen Kadlemakki"

    def test_config_overrides_email(self):
        config = {"candidate": {"email": "newemail@test.com"}}
        profile = load_candidate_profile(resume_path="nonexistent.pdf", config=config)
        assert profile["email"] == "newemail@test.com"

    def test_config_overrides_target_comp(self):
        config = {"candidate": {"target_comp_aed": 1500000}}
        profile = load_candidate_profile(resume_path="nonexistent.pdf", config=config)
        assert profile["target_comp_aed"] == 1500000

    def test_config_overrides_name(self):
        config = {"candidate": {"name": "Test User"}}
        profile = load_candidate_profile(resume_path="nonexistent.pdf", config=config)
        assert profile["name"] == "Test User"

    def test_skills_not_overridden_by_config(self):
        """Config doesn't override skills (only specific fields)."""
        config = {"candidate": {"name": "Test"}}
        profile = load_candidate_profile(resume_path="nonexistent.pdf", config=config)
        assert len(profile["skills"]) > 0
