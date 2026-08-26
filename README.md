# Job Vault - a local Data Vault pipeline for job postings

Scrapes job postings from multiple websites into a single local database,
keeps full history of every change, and exports ready-to-use files for a
Google Sheets / Looker Studio dashboard. Built as the classic "job
postings" example of the Data Vault 2.0 modeling approach described in
Nuhad Shaabani's article "Practical Introduction to Data Vault Modeling".

Everything runs locally on the machine. No cloud, no services, no keys
to manage - just Python + SQLite.

## Why this exists

Different websites expose the same concept (a job posting) in completely
different formats. This project normalizes them into one schema, joins
them with content-based MD5 hash keys (so the same company from different
sites collapses into one row without any manual mapping), and keeps every
historical version of every posting so trends over time can be analyzed.

## Architecture

```
Daily batch (cron, 9 AM)
        |
        v
scrape_all.py   fetch raw JSON from every source       -> staging/<source>_<date>.json
normalize.py    map each site's fields to ONE shape    -> staging/normalized_<date>.json
load_dv.py      insert into Data Vault schema,         -> jobvault.db
                append-only history, diff summary
export.py       write CSV views for the dashboard      -> export/*.csv
                                                          |
                                                          v
                                                Google Sheets / Looker Studio
```

## The Data Vault schema

Data Vault uses three entity types in the Core layer:

| Entity   | Role                                             | Example here                     |
|----------|--------------------------------------------------|----------------------------------|
| Hub      | business keys only, natural key hashed as PK     | `h_company`, `h_job`             |
| Link     | many-to-many relationship between hubs           | `l_job_company`                  |
| Satellite| descriptive attributes, append-only history      | `s_job` (one row per version)    |

Keys are `MD5` hashes of the normalized business key (uppercase + trim).
So `"Razorpay Software Private Limited"` and `"  RAZORPAY software private limited "`
both hash to the same key and join automatically - no ID registry needed.
This is the technique your senior pointed at when they said
"use MD5 hash to join, search karlena".

## History (the satellite rule)

Satellites never update or delete. When a posting's details change between
batches, a NEW row is appended with the batch's load date; the old row is
kept. Jobs that disappear from a site get a `status='closed'` row.

```
s_job for one job:
  batch 2026-08-27 | open   | title "Associate Manager, Solutions Engineering"
  batch 2026-08-28 | open   | title "Associate Manager, Solutions Engineering [EDITED]"
```

You query the current state via the `v_job_current` view, and have full
history underneath it for trend analysis.

## Setup and run

```bash
cd JobVault
uv venv .venv
uv pip install --python .venv/bin/python requests
.venv/bin/python scrape_all.py     # pull raw data
.venv/bin/python normalize.py      # one shape
.venv/bin/python load_dv.py        # load + history
.venv/bin/python export.py         # CSVs for the sheet
.venv/bin/python verify.py         # prove it works
```

One-liner daily: `./run_batch.sh` (this is what the cron runs at 09:00).

## Sources

| Source            | System        | How many jobs today |
|-------------------|---------------|---------------------|
| Razorpay          | Greenhouse API| ~23                 |
| CRED              | Lever API     | ~14                 |
| Zeta              | Lever API     | ~22                 |
| Freshworks        | SmartRecruiters API | ~100            |

Adding a new site = one scraping rule + one normalization adapter in
`normalize.py`. Nothing else changes.

## Frontend (Google Sheets / Looker Studio)

`export.py` writes CSV files to `export/`:

- `current_jobs.csv`   - every job open right now (the main dashboard table)
- `job_history.csv`    - every version of every posting ever seen
- `jobs_by_day.csv`    - jobs per company per batch day (trend chart)
- `jobs_by_company.csv`- open jobs per company

Upload the CSVs to Google Sheets (File -> Import -> "Upload",
or just open the .csv in Google Sheets), then build a Looker Studio
report on top. Because `job_history.csv` grows every day, trend charts
over weeks/months come for free.

## Project structure

```
JobVault/
  scrape_all.py   fetch raw JSON from all sources
  normalize.py    normalize different site formats into one shape
  load_dv.py      Data Vault load with append-only history + diff
  export.py       CSV export for the frontend
  verify.py       report/self-check of the warehouse state
  schema.sql      the Data Vault schema (hubs / links / satellites)
  run_batch.sh    one batch: scrape -> normalize -> load -> export
  staging/        raw scraped data (one file per source per day)
  export/         CSV views consumed by the dashboard
  jobvault.db     the SQLite database (system of record)
```

Growth path: add salary extraction, skill/qualification extraction into
their own satellites, OAuth upload straight into Google Sheets, and a
daily "what changed since yesterday" message.