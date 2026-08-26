"""Phase 1: scrape Razorpay jobs from the Greenhouse API.

Greenhouse is the hiring system Razorpay uses. It has a public
JSON API, which means we get clean structured data - no HTML
parsing needed. Perfect first source to learn the pipeline on.
"""
import json
from datetime import date
from pathlib import Path

import requests

# The API endpoint that lists all open jobs at Razorpay.
API_URL = "https://boards-api.greenhouse.io/v1/boards/razorpaysoftwareprivatelimited/jobs"

# Where raw scraped data goes. This is the start of our
# centralized storage: every source dumps its raw data here.
STAGING = Path(__file__).parent / "staging"
STAGING.mkdir(exist_ok=True)

print("Fetching jobs from Razorpay's Greenhouse board...")
resp = requests.get(API_URL, timeout=30)
resp.raise_for_status()  # stop loudly if the site rejects us

jobs = resp.json()["jobs"]
print(f"Got {len(jobs)} jobs")

# Save the raw response exactly as the API sent it.
# .json file per day = one file per batch, history of raw data.
out = STAGING / f"razorpay_{date.today().isoformat()}.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump(jobs, f, indent=2, ensure_ascii=False)
print(f"Saved raw data to: {out}")

# Show a sample so we can see what the data looks like.
print("\nSample jobs:")
for job in jobs[:5]:
    print("-", job["title"], "|", job["location"]["name"], "|", job["absolute_url"])