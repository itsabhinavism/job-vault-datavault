"""Prove the whole warehouse: counts, joins, company collapse, history.

Run after load_dv.py. Every number printed comes straight from the DB.
"""
import sqlite3

from load_dv import BATCH_DATE, md5_key

conn = sqlite3.connect("jobvault.db")
conn.row_factory = sqlite3.Row

print(f"== Warehouse report (latest batch {BATCH_DATE}) ==\n")

print("-- Row counts --")
for t in ["h_company", "h_job", "l_job_company", "s_job"]:
    n = conn.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"]
    label = "s_job (all versions ever)" if t == "s_job" else t
    print(f"  {label:24}: {n}")

print("\n-- Company hub: one row per REAL company, across all sites --")
for r in conn.execute("SELECT company_name, record_source FROM h_company ORDER BY company_name"):
    print(f"  {r['company_name']:35} <- {r['record_source']}")

cur = conn.execute(
    """
    SELECT company_name, title, location, strftime('%Y-%m-%d', first_published) AS posted
    FROM v_job_current WHERE status='open'
    ORDER BY company_name, posted LIMIT 12
    """
).fetchall()
print("\n-- Current view (today's state): jobs still open --")
for r in cur:
    print(f"  {r['company_name'][:22]:23} | {r['title'][:40]:41} | {r['location'][:16]:17} | {r['posted']}")

hist = conn.execute("SELECT hk_job, COUNT(*) AS v FROM s_job GROUP BY hk_job HAVING v > 1").fetchall()
print(f"\n-- History: {len(hist)} job(s) have more than one version in s_job --")
for h in hist[:3]:
    for v in conn.execute(
        "SELECT title, batch_date, status, updated_at FROM s_job WHERE hk_job=? ORDER BY load_date",
        (h["hk_job"],),
    ):
        print(f"    v-> {v['title'][:40]:41} | batch {v['batch_date']} | {v['status']} | src-updated {v['updated_at'][:10]}")

print("\n-- Change Data Capture: change_log events --")
for r in conn.execute("SELECT change_type, COUNT(*) AS n FROM change_log GROUP BY change_type ORDER BY n DESC"):
    print(f"  {r['change_type']:9}: {r['n']}")
print("  latest 3 events:")
for r in conn.execute("SELECT batch_date, change_type, title, changed_fields FROM change_log ORDER BY change_id DESC LIMIT 3"):
    print(f"    {r['batch_date']} | {r['change_type']:7} | {r['title'][:36]:37} | {str(r['changed_fields'])[:70]}")

print("\n-- Source watermarks (CDC incremental state) --")
for r in conn.execute("SELECT source, last_batch_date, last_changed_at, records_seen FROM source_watermarks ORDER BY source"):
    print(f"  {r['source']:32} | batch {r['last_batch_date']} | last src change {str(r['last_changed_at'])[:10]} | {r['records_seen']} records")

print("\n-- Extracted signals: top skills among open jobs --")
for r in conn.execute(
    """SELECT sk.skill_name, COUNT(*) AS jobs
       FROM l_job_skill l
       JOIN h_skill sk ON sk.hk_skill = l.hk_skill
       JOIN s_job s ON s.hk_job = l.hk_job
       WHERE s.status='open'
         AND s.load_date=(SELECT MAX(s2.load_date) FROM s_job s2 WHERE s2.hk_job = s.hk_job)
       GROUP BY sk.skill_name ORDER BY jobs DESC LIMIT 10"""
):
    print(f"  {r['skill_name']:16}: {r['jobs']} open jobs")

sal = conn.execute(
    """SELECT hc.company_name, s.title, sl.salary_min, sl.salary_max, sl.currency, sl.period
       FROM s_job_salary sl
       JOIN s_job s ON s.hk_job = sl.hk_job AND s.load_date = sl.load_date
       JOIN l_job_company l ON l.hk_job = sl.hk_job
       JOIN h_company hc ON hc.hk_company = l.hk_company
       WHERE s.status='open'
         AND s.load_date=(SELECT MAX(s2.load_date) FROM s_job s2 WHERE s2.hk_job = s.hk_job)
       ORDER BY sl.salary_max DESC LIMIT 5"""
).fetchall()
print("  top salaries found:")
for r in sal:
    print(f"    {r['company_name'][:18]:19} {r['title'][:30]:31} {str(r['currency'] or '?'):4} {r['salary_min']}-{r['salary_max']} ({r['period']})")

print("\n-- Why MD5 (the join trick) --")
a = md5_key("Razorpay Software Private Limited")
b = md5_key("  RAZORPAY software private limited ")
print(f"  same company, two spellings -> same key? {a == b}  ({a[:12]}...)")

conn.close()