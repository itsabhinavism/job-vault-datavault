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

# Country detection: full names/codes matched as WHOLE tokens only (never
# substring), so "in" can't match "BerlIN" and "berlin" can't hijack Hyderabad.
_COUNTRY_FULL = {
    "india": "India", "bharat": "India",
    "united states": "US", "usa": "US", "u.s.": "US", "america": "US",
    "united kingdom": "UK", "uk": "UK", "england": "UK",
    "germany": "Germany", "deutschland": "Germany",
    "singapore": "Singapore",
    "malaysia": "Malaysia",
    "united arab emirates": "UAE", "uae": "UAE", "dubai": "UAE",
    "netherlands": "Netherlands", "holland": "Netherlands",
    "france": "France", "spain": "Spain", "italy": "Italy", "canada": "Canada",
    "australia": "Australia", "brazil": "Brazil", "china": "China", "japan": "Japan",
    "poland": "Poland", "sweden": "Sweden", "switzerland": "Switzerland",
    "ireland": "Ireland", "israel": "Israel", "mexico": "Mexico", "argentina": "Argentina",
    "south africa": "South Africa", "south korea": "South Korea", "new zealand": "New Zealand",
}
# 2-letter ISO codes are only trusted as the LAST token ("hyderabad, in" ->
# India), so "CA"/"NY" regions inside US listings can't be mistaken.
_COUNTRY_CODE = {
    "in": "India", "us": "US", "uk": "UK", "gb": "UK",
    "de": "Germany", "sg": "Singapore", "my": "Malaysia", "ae": "UAE",
    "nl": "Netherlands", "fr": "France", "es": "Spain", "it": "Italy",
    "ca": "Canada", "au": "Australia", "cn": "China", "jp": "Japan",
    "pl": "Poland", "se": "Sweden", "ch": "Switzerland", "ie": "Ireland",
    "il": "Israel", "mx": "Mexico", "br": "Brazil", "za": "South Africa",
}
_JUNK_LOC = {"remote", "hybrid", "onsite", "on-site", "work from home", "wfh",
             "anywhere", "office", "india", "in", "us", "uk"}
# Whole raw value is just an Indian state -> "State, India".
_INDIAN_STATES = {"tamil nadu": "Tamil Nadu", "karnataka": "Karnataka",
                  "maharashtra": "Maharashtra", "telangana": "Telangana"}
INDIAN_CITIES = set(CITY_ALIASES.values())


def normalize_location(loc):
    """'bengaluru' / 'Bengaluru, in' / 'bangalore' -> 'Bengaluru, India'.

    Token-based: splits on separators, matches country names/codes as whole
    tokens only, and always appends ', India' for known Indian cities.
    """
    if not loc:
        return ""
    s = str(loc).strip().lower()
    if not s:
        return ""
    parts = [p.strip() for p in re.split(r"[/,;–—-]", s) if p.strip()]
    parts = [re.sub(r"[_\-]", " ", p) for p in parts]

    # 1) Country: prefer a full-name token anywhere; fall back to the LAST
    #    token if it is a 2-letter code (regions like "CA" are never last
    #    when the listing says "San Mateo, CA, United States").
    country = ""
    for p in parts:
        if p in _COUNTRY_FULL:
            country = _COUNTRY_FULL[p]
            break
    if not country and parts and parts[-1] in _COUNTRY_CODE:
        country = _COUNTRY_CODE[parts[-1]]

    # 2) City: first token that is not a country or junk word.
    city_raw = ""
    for p in parts:
        if p in _COUNTRY_FULL or p in _COUNTRY_CODE or p in _JUNK_LOC:
            continue
        city_raw = p
        break

    # 3) Raw was an Indian state on its own -> "State, India" wins over city
    #    title-casing ("tamil nadu" -> "Tamil Nadu, India", not "Tamil Nadu").
    if s in _INDIAN_STATES:
        return f"{_INDIAN_STATES[s]}, India"

    # 4) Raw was only a country name ("Malaysia", "Usa") -> just the country.
    if not city_raw and country:
        return country

    # 5) No city at all -> give the raw string back untouched.
    if not city_raw:
        return str(loc).strip()

    city = CITY_ALIASES.get(city_raw) or (city_raw.title() if city_raw else "")

    # 6) Known Indian city -> always ", India" (even if a broken source
    #    claimed a foreign country, the city wins).
    if city in INDIAN_CITIES:
        return f"{city}, India"

    # 7) Non-Indian city + detected country -> "City, Country".
    if city and country:
        return f"{city}, {country}"

    return city or str(loc).strip()


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