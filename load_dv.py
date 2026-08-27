"""Load normalized data with append-only HISTORY + CHANGE DATA CAPTURE (CDC).

For each job we keep EVERY version ever seen (append-only satellites).
On top of that, this loader implements CDC properly:

  - change_log:       one row per change EVENT (NEW / UPDATED / CLOSED),
                      with the field-level diff stored as JSON, so we can
                      answer "what changed, in which field, from what to
                      what, and when".
  - source_watermarks: per-source incremental state (last batch date, latest
                      source timestamp, records seen) - the foundation for
                      incremental extraction (pull only deltas next batch).

This is the answer to "you are just appending": append-only storage PLUS an
explicitly captured, queryable change feed.
"""
import hashlib
import json
import os
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent
# Optional override (used by tests/demos so the real DB is never touched).
DB = Path(os.environ.get("JOBVAULT_DB", str(BASE / "jobvault.db")))
# Optional command-line arg = which batch's normalized file to load.
BATCH_DATE = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
RAW = BASE / "staging" / f"normalized_{BATCH_DATE}.json"

# The descriptive fields we track for change capture.
CHANGE_FIELDS = ["title", "location", "url", "first_published", "updated_at"]


def md5_key(*parts):
    raw = "|".join(str(p).strip().upper() for p in parts)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def open_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.executescript((BASE / "schema.sql").read_text())  # create tables if missing
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


def cdc_diff(prev_row, rec):
    """Field-level change capture: {field: {from: x, to: y}} per changed field."""
    diff = {}
    for f in CHANGE_FIELDS:
        old = str(prev_row[f] or "")
        new = str(rec.get(f) or "")
        if old != new:
            diff[f] = {"from": old, "to": new}
    return json.dumps(diff, ensure_ascii=False) if diff else None


def log_change(conn, source, hk_job, change_type, changed_fields, title, stamp):
    conn.execute(
        "INSERT INTO change_log (batch_date, source, hk_job, change_type, changed_fields, title, occurred_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (BATCH_DATE, source, hk_job, change_type, changed_fields, title, stamp),
    )


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

    change_type = "NEW"
    changed_fields = None
    if prev is None or prev["status"] == "closed":
        stats["new"] += 1                     # brand-new posting (or reopened)
    else:
        prev_dets = (prev["title"], prev["location"], prev["url"], prev["first_published"], prev["updated_at"])
        if prev_dets == details:
            stats["unchanged"] += 1           # identical - no change event
            return
        stats["changed"] += 1                 # something changed - capture it
        change_type = "UPDATED"
        changed_fields = cdc_diff(prev, rec)

    conn.execute(
        """INSERT INTO s_job
           (hk_job, load_date, batch_date, title, location, url, first_published, updated_at, status, record_source)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (hk_job, stamp, BATCH_DATE, rec["title"], rec["location"], rec["url"],
         rec["first_published"], rec["updated_at"], "open", rec["source"]))

    # CDC: capture the change event.
    log_change(conn, rec["source"], hk_job, change_type, changed_fields, rec["title"], stamp)


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
    # CDC: capture the close event (DELETE-equivalent in change terms).
    log_change(conn, last["record_source"], hk_job, "CLOSED",
               json.dumps({"status": {"from": "open", "to": "closed"}}), last["title"], stamp)
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

    # CDC: update per-source watermarks (incremental extraction state).
    for src in sources_today:
        src_recs = [r for r in recs if r["source"] == src]
        last_changed = max((r.get("updated_at") or "" for r in src_recs), default="")
        conn.execute(
            "INSERT OR REPLACE INTO source_watermarks (source, last_batch_date, last_changed_at, records_seen) "
            "VALUES (?,?,?,?)",
            (src, BATCH_DATE, last_changed, len(src_recs)),
        )

    conn.commit()
    conn.close()
    print(f"Batch {BATCH_DATE} loaded (CDC changelog updated):")
    print(f"  New:       {stats['new']}")
    print(f"  Changed:   {stats['changed']}")
    print(f"  Unchanged: {stats['unchanged']}")
    print(f"  Closed:    {stats['closed']}")


if __name__ == "__main__":
    main()