"""Normalize all raw sources into ONE standard shape.

Every website has its own field names:
  Greenhouse: id, company_name, absolute_url, location.name, content (HTML)
  Lever:      id, text, hostedUrl, categories.location, createdAt (ms), descriptionPlain
  SmartRecruiters: id, name, ref, location.{city,country}, releasedDate, jobAd

This maps each one onto the SAME record shape so the database only ever
sees one format. It also:
  - strips the job description to plain text (for salary/skills extraction)
  - normalizes location alias spellings (bengaluru/Bangalore -> Bengaluru)
  - carries a work_mode hint (remote/hybrid/onsite) where the source provides it
"""
import html as _html
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent
STAGING = BASE / "staging"
TODAY = date.today().isoformat()


def strip_html(raw):
    if not raw:
        return ""
    s = re.sub(r"<[^>]+>", " ", str(raw))
    s = _html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


# Alias -> canonical city name (helps the dashboard group locations cleanly).
CITY_ALIASES = {
    "bengaluru": "Bengaluru", "bangalore": "Bengaluru", "banglore": "Bengaluru",
    "hyderabad": "Hyderabad", "hyderbad": "Hyderabad",
    "mumbai": "Mumbai", "bombay": "Mumbai",
    "chennai": "Chennai", "madras": "Chennai",
    "kolkata": "Kolkata", "delhi": "Delhi", "new delhi": "Delhi",
    "noida": "Noida", "gurugram": "Gurugram", "gurgaon": "Gurugram",
    "pune": "Pune", "indore": "Indore", "kochi": "Kochi", "coimbatore": "Coimbatore",
    "ahmedabad": "Ahmedabad", "jaipur": "Jaipur", "bhubaneswar": "Bhubaneswar",
    "patna": "Patna", "chandigarh": "Chandigarh", "lucknow": "Lucknow",
    "nagpur": "Nagpur", "visakhapatnam": "Visakhapatnam", "thane": "Thane",
    "goa": "Goa", "surat": "Surat",
}

_COUNTRY_HINTS = [
    ("in", "India"), ("india", "India"), ("gb", "UK"), ("uk", "UK"), ("london", "UK"),
    ("us", "US"), ("usa", "US"), ("de", "Germany"), ("germany", "Germany"),
    ("berlin", "Germany"), ("sg", "Singapore"), ("singapore", "Singapore"),
    ("uae", "UAE"), ("dubai", "UAE"), ("nl", "Netherlands"), ("fr", "France"),
    ("ae", "UAE"), ("malaysia", "Malaysia"), ("my", "Malaysia"),
]


def normalize_location(loc):
    """'bengaluru' / 'Bengaluru, in' / 'bangalore' -> 'Bengaluru, India'."""
    if not loc:
        return ""
    s = str(loc).strip().lower()
    if not s:
        return ""
    city = re.split(r"[/,;–—-]", s)[0].strip()
    city = re.sub(r"[_\-]", " ", city)
    country = ""
    for hint, name in _COUNTRY_HINTS:
        if hint in s:
            country = name
            break
    name = CITY_ALIASES.get(city) or (city.title() if city else "")
    if name and country:
        return f"{name}, {country}"
    return name or str(loc).strip()


def sr_description(j):
    ad = j.get("jobAd") or {}
    if isinstance(ad, dict) and "jobAd" in ad and ad.get("sections") is None:
        ad = ad["jobAd"]
    secs = ad.get("sections") or {}
    jobdesc = secs.get("jobDescription") or {}
    parts = [strip_html(jobdesc.get("text") or "")]
    for s in (jobdesc.get("sections") or []):
        if isinstance(s, dict):
            parts.append(strip_html(s.get("text") or ""))
    return " ".join(p for p in parts if p)[:6000]


def ts_iso(ms):
    # Lever sends time as milliseconds since 1970 - convert to readable UTC.
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def gh_record(j):
    return {
        "source": "greenhouse_razorpay", "source_job_id": str(j["id"]),
        "title": j["title"], "company_name": j["company_name"],
        "location": normalize_location((j.get("location") or {}).get("name") or ""),
        "url": j["absolute_url"], "first_published": j.get("first_published"), "updated_at": j.get("updated_at"),
        "description": strip_html(j.get("content") or ""),
        "work_mode": "",
    }


def lever_record(j, company):
    return {
        "source": "lever_" + company, "source_job_id": j["id"],
        "title": j.get("text"), "company_name": company.title(),
        "location": normalize_location((j.get("categories") or {}).get("location") or j.get("country") or ""),
        "url": j.get("hostedUrl"), "first_published": ts_iso(j["createdAt"]), "updated_at": ts_iso(j["createdAt"]),
        "description": (j.get("descriptionPlain") or strip_html(j.get("description") or ""))[:6000],
        "work_mode": j.get("workplaceType") or "",
    }


def sr_record(j):
    loc = j.get("location") or {}
    city = loc.get("city") or ""
    country = loc.get("country") or ""
    raw_company = j.get("company")
    if isinstance(raw_company, dict):
        company = raw_company.get("name") or raw_company.get("id") or "Freshworks"
    else:
        company = raw_company or "Freshworks"
    ts = j.get("releasedDate") or j.get("postingDate") or ""
    return {
        "source": "smartrecruiters_freshworks", "source_job_id": str(j["id"]),
        "title": j.get("name"), "company_name": company,
        "location": normalize_location(f"{city}, {country}".strip(", ").strip()),
        "url": f"https://jobs.smartrecruiters.com/{company}/{j['id']}",
        "first_published": ts, "updated_at": ts,
        "description": sr_description(j),
        "work_mode": "",
    }


# Each source gets its own adapter. Adding a new website = one new entry here.
ADAPTERS = {
    "greenhouse_razorpay": lambda jobs: [gh_record(j) for j in jobs],
    "lever_cred": lambda jobs: [lever_record(j, "cred") for j in jobs],
    "lever_zeta": lambda jobs: [lever_record(j, "zeta") for j in jobs],
    "smartrecruiters_freshworks": lambda jobs: [sr_record(j) for j in jobs],
}


def main():
    records = []
    per_source = {}
    for name, adapt in ADAPTERS.items():
        f = STAGING / f"{name}_{TODAY}.json"
        if not f.exists():
            print(f"SKIP {name} (no raw file yet - run scrape_all.py first)")
            continue
        recs = adapt(json.loads(f.read_text(encoding="utf-8")))
        records += recs
        per_source[name] = len(recs)
        with_desc = sum(1 for r in recs if r.get("description"))
        print(f"{name}: normalized {len(recs)} ({with_desc} with description)")

    out = STAGING / f"normalized_{TODAY}.json"
    out.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nTOTAL normalized: {len(records)}  ->  {out.name}")
    print("Per source:", per_source)


if __name__ == "__main__":
    main()