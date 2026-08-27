"""Tests for the signal-extraction parsers (salary / skills / mode / level)."""
import features


def test_salary_inr_lpa():
    r = features.parse_salary("We pay Rs 5 - 8 LPA depending on experience.")
    assert r is not None
    assert r["min"] == 5.0 and r["max"] == 8.0
    assert r["currency"] == "INR" and r["period"] == "annual"


def test_salary_usd_k():
    r = features.parse_salary("Salary range: $80k - $120k per year.")
    assert r is not None
    assert r["min"] == 80000.0 and r["max"] == 120000.0
    assert r["currency"] == "USD" and r["period"] == "annual"


def test_salary_none():
    assert features.parse_salary("Join our amazing team!") is None
    assert features.parse_salary(None) is None
    assert features.parse_salary("") is None


def test_salary_monthly():
    r = features.parse_salary("4000 - 5000 per month")
    assert r is not None
    assert r["period"] == "monthly"


def test_salary_not_experience_years():
    # "5 to 10 years" is experience, not a salary - must not match.
    assert features.parse_salary("5 to 10 years of experience required") is None


def test_skills_detection():
    sk = features.parse_skills("You will use Python, SQL and Power BI daily. AWS is a plus.")
    skset = set(sk)
    assert "python" in skset and "sql" in skset and "power bi" in skset and "aws" in skset


def test_skills_empty():
    assert features.parse_skills("") == []
    assert features.parse_skills(None) == []


def test_work_mode_remote():
    assert features.detect_work_mode("This is a fully remote position.", "") == "remote"
    assert features.detect_work_mode("", "remote") == "remote"
    assert features.detect_work_mode("Work from home allowed", "") == "remote"


def test_work_mode_hybrid_and_onsite():
    assert features.detect_work_mode("Hybrid - 3 days in office", "") == "hybrid"
    assert features.detect_work_mode("Onsite only", "") == "onsite"
    assert features.detect_work_mode("do great things", "") == "unknown"


def test_level():
    assert features.extract_level("Senior Software Engineer") == "senior"
    assert features.extract_level("Lead Data Scientist") == "lead"
    assert features.extract_level("Principal Solution Engineer") == "principal"
    assert features.extract_level("Financial Analyst") == "associate"
    assert features.extract_level("Director of Engineering") == "management"
    assert features.extract_level("Vice President - Sales") == "management"