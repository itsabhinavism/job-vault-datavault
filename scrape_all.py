"""Phase 3: scrape ALL sources into raw staging files.

One file per source per day. This is the "batch" in batch processing:
every run today replaces today's file with a fresh pull.
"""
import json
from datetime import date
from pathlib import Path

import requests

BASE = Path(__file__).parent
STAGING = BASE / "staging"
STAGING.mkdir(exist_ok=True)
TODAY = date.today().isoformat()
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"}


def fetch_gh(board):   # Greenhouse (Razorpay uses it)
    # The API returns {"jobs": [...], "meta": {...}} - we only need the list.
    return requests.get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs", headers=UA, timeout=30).json()["jobs"]


def fetch_lever(company):   # Lever (CRED, Zeta)
    return requests.get(f"https://api.lever.co/v0/postings/{company}?mode=json", headers=UA, timeout=30).json()


def fetch_sr(company):   # SmartRecruiters (Freshworks)
    return requests.get(f"https://api.smartrecruiters.com/v1/companies/{company}/postings?limit=100", headers=UA, timeout=30).json()["content"]


SOURCES = {
    "greenhouse_razorpay": lambda: fetch_gh("razorpaysoftwareprivatelimited"),
    "lever_cred": lambda: fetch_lever("cred"),
    "lever_zeta": lambda: fetch_lever("zeta"),
    "smartrecruiters_freshworks": lambda: fetch_sr("Freshworks"),
}

total = 0
for name, fetch in SOURCES.items():
    try:
        data = fetch()
        n = len(data)
        total += n
        out = STAGING / f"{name}_{TODAY}.json"
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{name}: {n} jobs  ->  {out.name}")
    except Exception as e:
        print(f"{name}: ERROR {e}")

print(f"TOTAL raw scraped across all sites: {total}")