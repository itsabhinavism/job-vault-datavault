"""Phase 4: load normalized data with append-only HISTORY + diff summary.

For each job we keep EVERY version ever seen. If a job's details change
between batches (e.g. salary or location edited), we ADD a new satellite
row - we never overwrite the old one. Today's batch becomes the 'current'
view; every older row stays as history. Jobs that disappear from a site
get a status='closed' row.

This is exactly the Data Vault satellite rule from the article:
"Existing records are never updated or deleted."
"""
import hashlib
import json
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent
DB = BASE / "jobvault.db"
# Optional command-line arg = which batch's normalized file to load.
# Defaults to today. Passing a date lets us replay older batches.
BATCH_DATE = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
RAW = BASE / "staging" / f"normalized_{BATCH_DATE}.json"


def md5_key(*parts):
    raw = "|".join(str(p).strip().upper() for p in parts)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def now():
    # Microsecond precision so two batches in the same second can't collide
    # on the satellite primary key (hk_job, load_date).
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def open_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.executescript((BASE / "schema.sql").read_text())  # create tables if missing
    # 'current' view = the most recent satellite row per job (today's state).
    conn.executescript("""
    DROP VIEW IF EXISTS v_job_current;
    CREATE VIEW v_job_current AS
    SELECT hj.source, hj.source_job_id, s.title, hc.company_name,
           s.location, s.url, s.first_published, s.updated_at,
           s.batch_date, s.status
    FROM s_job s
    JOIN h_job hj        ON hj.hk_job = s.hk_job
    JOIN l_job_company l ON l.hk_job = hj.hk_job
    JOIN h_company hc    ON hc.hk_company = l.hk_company
    WHERE s.load_date = (SELECT MAX(s2.load_date) FROM s_job s2 WHERE s2.hk_job = s.hk_job)
    """)
    return conn


def latest_satellite(conn, hk_job):
    return conn.execute(
        "SELECT title, location, url, first_published, updated_at, status, record_source "
        "FROM s_job WHERE hk_job=? ORDER BY load_date DESC LIMIT 1", (hk_job,)).fetchone()


def load_record(conn, rec, stamp, stats):
    job_id = rec["source_job_id"]
    company_bk = rec["company_name"].strip().upper()
    hk_job = md5_key(rec["source"], job_id)
    hk_company = md5_key(company_bk)

    # Hubs + link are idempotent - INSERT OR IGNORE means "already there, skip".
    conn.execute(
        "INSERT OR IGNORE INTO h_company (hk_company, company_name, load_date, record_source) VALUES (?,?,?,?)",
        (hk_company, company_bk, stamp, rec["source"]))
    conn.execute(
        "INSERT OR IGNORE INTO h_job (hk_job, source, source_job_id, load_date, record_source) VALUES (?,?,?,?,?)",
        (hk_job, rec["source"], job_id, stamp, rec["source"]))
    conn.execute(
        "INSERT OR IGNORE INTO l_job_company (lhk_job_company, hk_job, hk_company, load_date) VALUES (?,?,?,?)",
        (md5_key(hk_job, hk_company), hk_job, hk_company, stamp))

    details = (rec["title"], rec["location"], rec["url"], rec["first_published"], rec["updated_at"])
    prev = latest_satellite(conn, hk_job)

    if prev is None or prev["status"] == "closed":
        stats["new"] += 1                     # brand-new posting (or reopened)
    else:
        prev_dets = (prev["title"], prev["location"], prev["url"], prev["first_published"], prev["updated_at"])
        if prev_dets == details:
            stats["unchanged"] += 1           # identical - store nothing new
            return
        stats["changed"] += 1                 # something changed - store a new version

    conn.execute(
        """INSERT INTO s_job
           (hk_job, load_date, batch_date, title, location, url, first_published, updated_at, status, record_source)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (hk_job, stamp, BATCH_DATE, rec["title"], rec["location"], rec["url"],
         rec["first_published"], rec["updated_at"], "open", rec["source"]))


def mark_closed(conn, hk_job, stamp):
    last = latest_satellite(conn, hk_job)
    if last is None or last["status"] == "closed":
        return 0
    conn.execute(
        """INSERT INTO s_job
           (hk_job, load_date, batch_date, title, location, url, first_published, updated_at, status, record_source)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (hk_job, stamp, BATCH_DATE, last["title"], last["location"], last["url"],
         last["first_published"], last["updated_at"], "closed", last["record_source"]))
    return 1


def main():
    recs = json.loads(RAW.read_text(encoding="utf-8"))
    if not recs:
        print("No normalized records - run scrape_all.py + normalize.py first")
        return

    stats = {"new": 0, "changed": 0, "unchanged": 0, "closed": 0}
    sources_today = {r["source"] for r in recs}                    # only these get closed-checks
    today_keys = {(r["source"], r["source_job_id"]) for r in recs}

    stamp = now()
    conn = open_db()

    for rec in recs:
        load_record(conn, rec, stamp, stats)

    # Known jobs from a scraped-today source but absent today -> closed.
    for src, jid, hk in conn.execute("SELECT source, source_job_id, hk_job FROM h_job"):
        if src in sources_today and (src, jid) not in today_keys:
            stats["closed"] += mark_closed(conn, hk, stamp)

    conn.commit()
    conn.close()
    print(f"Batch {BATCH_DATE} loaded:")
    print(f"  New:       {stats['new']}")
    print(f"  Changed:   {stats['changed']}")
    print(f"  Unchanged: {stats['unchanged']}")
    print(f"  Closed:    {stats['closed']}")


if __name__ == "__main__":
    main()