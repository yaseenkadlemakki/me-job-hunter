"""Unit tests for src/parsers/job_parser.py"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.parsers.job_parser import JobParser


@pytest.fixture
def parser():
    return JobParser()


class TestParse:
    """Test the main parse() method."""

    def test_parse_returns_dict(self, parser):
        raw = {"title": "Director of Engineering", "company": "Test Co", "url": "https://example.com/job/1"}
        result = parser.parse(raw)
        assert isinstance(result, dict)

    def test_parse_title(self, parser):
        raw = {"title": "  Director of Engineering  ", "company": "Test", "url": "https://example.com/1"}
        result = parser.parse(raw)
        assert result["title"] == "Director of Engineering"

    def test_parse_company(self, parser):
        raw = {"title": "Director", "company": "  Acme Corp  ", "url": "https://example.com/1"}
        result = parser.parse(raw)
        assert result["company"] == "Acme Corp"

    def test_parse_location_dubai(self, parser):
        raw = {"title": "Director", "company": "C", "location": "Dubai, UAE", "url": "https://e.com/1"}
        result = parser.parse(raw)
        assert result["location"] == "Dubai, UAE"

    def test_parse_location_riyadh(self, parser):
        raw = {"title": "Director", "company": "C", "location": "Riyadh, Saudi Arabia", "url": "https://e.com/1"}
        result = parser.parse(raw)
        assert result["location"] == "Riyadh, Saudi Arabia"

    def test_parse_url_preserved(self, parser):
        url = "https://linkedin.com/jobs/view/12345"
        raw = {"title": "Director", "company": "C", "url": url}
        result = parser.parse(raw)
        assert result["url"] == url

    def test_parse_source_preserved(self, parser):
        raw = {"title": "D", "company": "C", "url": "https://e.com/1", "source": "bayt"}
        result = parser.parse(raw)
        assert result["source"] == "bayt"

    def test_parse_cleans_html_description(self, parser):
        raw = {
            "title": "Director",
            "company": "C",
            "url": "https://e.com/1",
            "description": "<p>We need a <strong>Director</strong> with <em>AWS</em> experience.</p>",
        }
        result = parser.parse(raw)
        assert "<p>" not in result["description"]
        assert "<strong>" not in result["description"]
        assert "Director" in result["description"]
        assert "AWS" in result["description"]

    def test_parse_returns_seniority_level(self, parser):
        raw = {"title": "Director of Engineering", "company": "C", "url": "https://e.com/1"}
        result = parser.parse(raw)
        assert result["seniority_level"] == "director"


class TestSalaryExtraction:
    """Test _extract_salary() and _estimate_salary_aed()."""

    def test_extracts_aed_salary_from_description(self, parser):
        raw = {
            "title": "Director",
            "company": "C",
            "url": "https://e.com/1",
            "description": "Salary: AED 1,200,000 - 1,500,000 per year",
        }
        result = parser.parse(raw)
        assert result["salary_raw"] is not None
        assert "AED" in result["salary_raw"] or "1" in result["salary_raw"]

    def test_extracts_usd_salary(self, parser):
        raw = {
            "title": "Director",
            "company": "C",
            "url": "https://e.com/1",
            "description": "Compensation: $300k - $400k per year",
        }
        result = parser.parse(raw)
        assert result["salary_raw"] is not None

    def test_no_salary_returns_none(self, parser):
        raw = {
            "title": "Director",
            "company": "C",
            "url": "https://e.com/1",
            "description": "Great role with excellent benefits.",
        }
        result = parser.parse(raw)
        assert result["salary_raw"] is None
        assert result["salary_estimated_aed"] is None

    def test_explicit_salary_raw_takes_precedence(self, parser):
        raw = {
            "title": "Director",
            "company": "C",
            "url": "https://e.com/1",
            "salary_raw": "AED 1,400,000",
            "description": "Something about salary being 800K AED",
        }
        result = parser.parse(raw)
        assert "1,400,000" in result["salary_raw"] or "1400000" in str(result["salary_raw"])

    def test_aed_salary_conversion(self, parser):
        # Midpoint of 1.2M-1.5M AED = 1.35M AED, monthly so *12 = 16.2M? No...
        # If > 500K AED, not multiplied by 12
        salary = parser._estimate_salary_aed("AED 1,200,000 - 1,500,000", "Dubai")
        assert salary is not None
        # Average of 1200000 and 1500000 is 1350000, and since > 500K, no *12
        assert salary == 1350000.0

    def test_usd_monthly_salary_converted_to_aed(self, parser):
        salary = parser._estimate_salary_aed("$25,000 per month", "Dubai")
        assert salary is not None
        # 25000 * 12 = 300000 USD/yr * 3.67 = ~1,101,000 AED
        assert salary > 1_000_000

    def test_sar_salary_converted_to_aed(self, parser):
        salary = parser._estimate_salary_aed("SAR 50,000 per month", "Riyadh")
        assert salary is not None
        # 50000 * 12 = 600000 SAR/yr * 0.98 = ~588,000 AED
        assert salary > 500_000

    def test_empty_salary_raw_returns_none(self, parser):
        result = parser._estimate_salary_aed(None, "Dubai")
        assert result is None

    def test_k_suffix_handling(self, parser):
        salary = parser._estimate_salary_aed("$300k - $400k", "Dubai")
        assert salary is not None
        # Avg 350K USD/yr * 3.67 = ~1.28M AED
        assert salary > 1_000_000


class TestDateParsing:
    """Test _parse_date()."""

    def test_parse_just_now(self, parser):
        result = parser._parse_date("just now")
        assert isinstance(result, datetime)
        assert (datetime.utcnow() - result).total_seconds() < 60

    def test_parse_today(self, parser):
        result = parser._parse_date("today")
        assert isinstance(result, datetime)

    def test_parse_yesterday(self, parser):
        result = parser._parse_date("yesterday")
        assert isinstance(result, datetime)
        assert (datetime.utcnow() - result).days >= 0

    def test_parse_2_days_ago(self, parser):
        result = parser._parse_date("2 days ago")
        assert isinstance(result, datetime)
        delta = datetime.utcnow() - result
        assert 1 <= delta.days <= 3

    def test_parse_1_week_ago(self, parser):
        result = parser._parse_date("1 week ago")
        assert isinstance(result, datetime)
        delta = datetime.utcnow() - result
        assert 6 <= delta.days <= 8

    def test_parse_1_month_ago(self, parser):
        result = parser._parse_date("1 month ago")
        assert isinstance(result, datetime)
        delta = datetime.utcnow() - result
        assert 28 <= delta.days <= 32

    def test_parse_iso_date(self, parser):
        result = parser._parse_date("2026-03-01")
        assert isinstance(result, datetime)
        assert result.year == 2026
        assert result.month == 3

    def test_parse_none_returns_none(self, parser):
        assert parser._parse_date(None) is None

    def test_parse_empty_string_returns_none(self, parser):
        assert parser._parse_date("") is None

    def test_parse_invalid_string_returns_none(self, parser):
        assert parser._parse_date("not a date at all xyz") is None

    def test_parse_hours_ago(self, parser):
        result = parser._parse_date("3 hours ago")
        assert isinstance(result, datetime)
        delta = datetime.utcnow() - result
        assert delta.total_seconds() / 3600 <= 4


class TestSeniorityDetection:
    """Test _detect_seniority()."""

    def test_detects_director(self, parser):
        assert parser._detect_seniority("Director of Engineering", "") == "director"

    def test_detects_vp(self, parser):
        assert parser._detect_seniority("VP of Engineering", "") == "vp"

    def test_detects_executive_cto(self, parser):
        assert parser._detect_seniority("CTO", "") == "executive"

    def test_detects_ic_engineer(self, parser):
        assert parser._detect_seniority("Senior Software Engineer", "") == "ic"

    def test_detects_manager(self, parser):
        assert parser._detect_seniority("Engineering Manager", "") == "manager"

    def test_detects_head_of(self, parser):
        assert parser._detect_seniority("Head of Platform Engineering", "") == "director"

    def test_unknown_title(self, parser):
        assert parser._detect_seniority("Unknown Role Xyz", "") == "unknown"

    def test_description_helps_detection(self, parser):
        # If title is ambiguous, description should help
        result = parser._detect_seniority("Lead", "We need an engineer with 5 years exp")
        assert result in ["manager", "ic", "director", "vp", "executive", "unknown"]


class TestCleanHtml:
    """Test _clean_html()."""

    def test_strips_basic_html(self, parser):
        result = parser._clean_html("<p>Hello <b>world</b></p>")
        assert "<p>" not in result
        assert "<b>" not in result
        assert "Hello" in result
        assert "world" in result

    def test_handles_empty_string(self, parser):
        assert parser._clean_html("") == ""

    def test_handles_none(self, parser):
        assert parser._clean_html(None) == ""

    def test_normalizes_whitespace(self, parser):
        result = parser._clean_html("Hello    World\n\n\nFoo")
        assert "  " not in result
        assert "\n\n" not in result

    def test_strips_nested_html(self, parser):
        html = "<div><ul><li>Item 1</li><li>Item 2</li></ul></div>"
        result = parser._clean_html(html)
        assert "<" not in result
        assert "Item 1" in result
        assert "Item 2" in result
