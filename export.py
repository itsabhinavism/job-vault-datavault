"""Phase 5: export the warehouse to CSV files for Google Sheets / Looker Studio.

The database is the system of record. These CSVs are the READ-ONLY
views that the frontend (Google Sheets, Looker Studio) consumes.
utf-8-sig adds a byte-order mark so Sheets and Excel open special
characters (like currency symbols) correctly.
"""
import csv
import sqlite3
from datetime import date
from pathlib import Path

BASE = Path(__file__).parent
DB = BASE / "jobvault.db"
OUT = BASE / "export"
OUT.mkdir(exist_ok=True)
TODAY = date.today().isoformat()


def dump(cursor, filename, rows):
    path = OUT / filename
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow([d[0] for d in cursor.description])
        w.writerows(rows)
    return path, len(rows)


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    files = {}

    # 1) Current open jobs - the main dashboard table.
    files["current_jobs.csv"] = dump(c,
        "current_jobs.csv",
        c.execute(
            """SELECT company_name, title, location, url, first_published,
                      strftime('%Y-%m-%d', first_published) AS posted,
                      batch_date, status
               FROM v_job_current WHERE status='open'
               ORDER BY company_name, posted""").fetchall())

    # 2) Full history - every version of every job ever seen.
    files["job_history.csv"] = dump(c,
        "job_history.csv",
        c.execute(
            """SELECT batch_date, source, source_job_id, company_name, title,
                      location, status
               FROM v_job_current
               UNION ALL
               SELECT s.batch_date, hj.source, hj.source_job_id, hc.company_name,
                      s.title, s.location, s.status
               FROM s_job s
               JOIN h_job hj ON hj.hk_job = s.hk_job
               JOIN l_job_company l ON l.hk_job = hj.hk_job
               JOIN h_company hc ON hc.hk_company = l.hk_company
               WHERE s.batch_date != ?
               ORDER BY batch_date, company_name""", (TODAY,)).fetchall())

    # 3) Jobs per company per day - the trend chart.
    files["jobs_by_day.csv"] = dump(c,
        "jobs_by_day.csv",
        c.execute(
            """SELECT batch_date, company_name, status, COUNT(*) AS jobs
               FROM (
                 SELECT s.batch_date, hc.company_name, s.status
                 FROM s_job s
                 JOIN h_job hj ON hj.hk_job = s.hk_job
                 JOIN l_job_company l ON l.hk_job = hj.hk_job
                 JOIN h_company hc ON hc.hk_company = l.hk_company
               )
               GROUP BY batch_date, company_name, status
               ORDER BY batch_date, company_name""").fetchall())

    # 4) Jobs currently open in each company.
    files["jobs_by_company.csv"] = dump(c,
        "jobs_by_company.csv",
        c.execute(
            """SELECT company_name, COUNT(*) AS open_jobs
               FROM v_job_current WHERE status='open'
               GROUP BY company_name ORDER BY open_jobs DESC""").fetchall())

    conn.close()

    print(f"Exported {TODAY} to {OUT}/")
    for name, (path, n) in files.items():
        print(f"  {name}: {n} rows")


if __name__ == "__main__":
    main()