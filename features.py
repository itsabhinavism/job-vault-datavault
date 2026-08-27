"""Extract structured signals from raw job data.

Pure standard library (re) so it runs anywhere and is easy to unit-test:
  - salary:     currency-agnostic range parser (INR LPA, USD/GBP/EUR k, /year, /month)
  - skills:     keyword tagging against the description
  - work mode:  remote / hybrid / onsite detection
  - level:      seniority tier from the job title
"""
import re

CURRENCY_SYMBOLS = {"$": "USD", "£": "GBP", "€": "EUR", "₹": "INR"}


def parse_salary(text):
    """Return {min, max, currency, period, raw} or None when no salary is mentioned."""
    if not text:
        return None
    t = str(text).replace("\u00a0", " ").lower().replace(",", "")

    # India: "₹5-8 LPA", "Rs 8 - 12 LPA", "INR 5 LPA" (values in lakhs, annual)
    m = re.search(r"(?:₹|rs\.?\s*|inr\s*)?([\d.]+)\s*(?:-|–|to)\s*([\d.]+)\s*(lpa|lakhs?|l/pa)", t)
    if m:
        return {"min": float(m.group(1)), "max": float(m.group(2)),
                "currency": "INR", "period": "annual", "raw": m.group(0).strip()}
    m = re.search(r"([\d.]+)\s*(?:-|–|to)\s*([\d.]+)\s*lpa", t)
    if m:
        return {"min": float(m.group(1)), "max": float(m.group(2)),
                "currency": "INR", "period": "annual", "raw": m.group(0).strip()}

    # "USD/GBP/EUR + k": "$80k - $120k", "£45k to £55k", "$90k"
    m = re.search(r"([$£€])\s?([\d.]+)\s*k?\s*(?:-|–|to)\s*[$£€]?\s*([\d.]+)\s*k", t)
    if m:
        return {"min": float(m.group(2)) * 1000, "max": float(m.group(3)) * 1000,
                "currency": CURRENCY_SYMBOLS[m.group(1)], "period": "annual", "raw": m.group(0).strip()}
    m = re.search(r"([$£€])\s?([\d.]+)\s*k", t)
    if m:
        return {"min": float(m.group(2)) * 1000, "max": float(m.group(2)) * 1000,
                "currency": CURRENCY_SYMBOLS[m.group(1)], "period": "annual", "raw": m.group(0).strip()}

    # Plain ranges with a period word: "45000-55000 per year", "3000-4000 per month"
    # (word boundaries so "5 to 10 years experience" is NOT read as salary)
    m = re.search(r"([\d.]+)\s*(?:-|–|to)\s*([\d.]+)\s*(?:/|per\s)?(year\b|annum|annual|pa\b|month\b|mo\b)", t)
    if m:
        period = "monthly" if m.group(3) in ("month", "mo") else "annual"
        return {"min": float(m.group(1)), "max": float(m.group(2)),
                "currency": None, "period": period, "raw": m.group(0).strip()}
    return None


SKILLS = [
    "python", "sql", "excel", "power bi", "tableau", "aws", "azure", "gcp",
    "spark", "kafka", "airflow", "dbt", "docker", "kubernetes", "tensorflow",
    "pytorch", "pandas", "numpy", "databricks", "snowflake", "postgresql",
    "postgres", "mysql", "mongodb", "redis", "git", "jira", "linux", "java",
    "c++", "c#", "javascript", "typescript", "react", "node.js", "flutter",
    "dart", "hadoop", "scala", "machine learning", "deep learning", "nlp",
    "etl", "data modeling", "dax", "power query", "looker", "sap", "salesforce",
    "scrum", "agile", "selenium", "ci/cd", "github actions", "mlops", "linux",
    "elasticsearch", "graphql", "rest api", "fastapi", "flask", "django",
]


def parse_skills(text):
    """Return the list of recognized skills found in the description."""
    if not text:
        return []
    t = " " + str(text).lower() + " "
    found = []
    for sk in SKILLS:
        if re.search(r"\b" + re.escape(sk) + r"\b", t):
            found.append(sk)
    # dedupe while keeping order
    seen = set()
    return [s for s in found if not (s in seen or seen.add(s))]


def detect_work_mode(description, hint=None):
    """remote / hybrid / onsite / unknown. hint can come from the source API."""
    if hint and hint.strip().lower() in ("remote", "hybrid", "onsite"):
        return hint.strip().lower()
    t = (description or "").lower()
    if any(k in t for k in ("work from home", "wfh", "fully remote", "remote-first", "remote position", "100% remote")):
        return "remote"
    if "remote" in t:
        return "remote"
    if "hybrid" in t:
        return "hybrid"
    if any(k in t for k in ("onsite", "on-site", "in office", "office based")):
        return "onsite"
    return "unknown"


_LEVEL_RULES = [
    ("management", ("vice president", "vp", "director", "head ", "chief", "cfo", "cto", "ceo")),
    ("principal", ("principal",)),
    ("staff", ("staff",)),
    ("lead", ("lead ", "lead-", "team lead")),
    ("senior", ("senior", "sr.", " sr ")),
    ("manager", ("manager",)),
    ("intern", ("intern",)),
    ("junior", ("junior", "jr.", "fresher")),
]


def extract_level(title):
    """associate/junior/intern/manager/senior/lead/staff/principal/management from a job title."""
    t = " " + (title or "").lower() + " "
    for level, keys in _LEVEL_RULES:
        for k in keys:
            if k in t:
                return level
    return "associate"