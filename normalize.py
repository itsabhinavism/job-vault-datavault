"""Phase 3: normalize all raw sources into ONE standard shape.

Every website has its own field names:
  Greenhouse: id, company_name, absolute_url, location.name
  Lever:      id, text, hostedUrl, categories.location, createdAt (milliseconds)
  SmartRecruiters: id, name, ref, location.{city,country}, releasedDate

This script maps each one onto the SAME record shape so the database
only ever sees one format. This is the "normalize different data"
step your senior described.
"""
import json
from datetime import date, datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent
STAGING = BASE / "staging"
TODAY = date.today().isoformat()


def ts_iso(ms):
    # Lever sends time as milliseconds since 1970 - convert to readable UTC.
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def gh_record(j):
    return {
        "source": "greenhouse_razorpay", "source_job_id": str(j["id"]),
        "title": j["title"], "company_name": j["company_name"],
        "location": (j.get("location") or {}).get("name") or "",
        "url": j["absolute_url"], "first_published": j.get("first_published"), "updated_at": j.get("updated_at"),
    }


def lever_record(j, company):
    return {
        "source": "lever_" + company, "source_job_id": j["id"],
        "title": j.get("text"), "company_name": company.title(),
        "location": (j.get("categories") or {}).get("location") or j.get("country") or "",
        "url": j.get("hostedUrl"), "first_published": ts_iso(j["createdAt"]), "updated_at": ts_iso(j["createdAt"]),
    }


def sr_record(j):
    loc = j.get("location") or {}
    city = loc.get("city") or ""
    country = loc.get("country") or ""
    # SmartRecruiters 'company' can be a string OR an object - handle both.
    raw_company = j.get("company")
    if isinstance(raw_company, dict):
        company = raw_company.get("name") or raw_company.get("id") or "Freshworks"
    else:
        company = raw_company or "Freshworks"
    ts = j.get("releasedDate") or j.get("postingDate") or ""
    return {
        "source": "smartrecruiters_freshworks", "source_job_id": str(j["id"]),
        "title": j.get("name"), "company_name": company,
        "location": f"{city}, {country}".strip(", ").strip(),
        "url": f"https://jobs.smartrecruiters.com/{company}/{j['id']}",
        "first_published": ts, "updated_at": ts,
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
        print(f"{name}: normalized {len(recs)}")

    out = STAGING / f"normalized_{TODAY}.json"
    out.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nTOTAL normalized: {len(records)}  ->  {out.name}")
    print("Per source:", per_source)


if __name__ == "__main__":
    main()