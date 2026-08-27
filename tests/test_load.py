"""End-to-end-ish tests for the loader against throwaway DBs:
a new record must produce a satellite row, an NEW change-log event,
and extracted salary/skills/meta rows. Each test uses its own job id
(assertions are scoped per job so tests can share the temp database file).
"""
import os
import tempfile
from datetime import datetime, timezone

_tmp = tempfile.mkdtemp()
os.environ["JOBVAULT_DB"] = os.path.join(_tmp, "test.db")   # must be set BEFORE import

import load_dv  # noqa: E402


def _stamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def _rec(job_id, title):
    return {
        "source": "test_src", "source_job_id": job_id,
        "title": title, "company_name": "Test Corp",
        "location": "Bengaluru", "url": f"http://example.com/job/{job_id}",
        "first_published": "2026-01-01T00:00:00Z", "updated_at": "2026-01-02T00:00:00Z",
        "description": "Python, SQL and Power BI. Salary 8-12 LPA. Fully remote.",
        "work_mode": "remote",
    }


def test_load_record_captures_everything():
    conn = load_dv.open_db()
    rec = _rec("1", "Senior Data Engineer")
    hk = load_dv.md5_key("test_src", "1")
    stats = {"new": 0, "changed": 0, "unchanged": 0, "closed": 0}
    load_dv.load_record(conn, rec, _stamp(), stats)
    conn.commit()

    assert conn.execute("SELECT COUNT(*) FROM s_job WHERE hk_job=?", (hk,)).fetchone()[0] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM change_log WHERE hk_job=? AND change_type='NEW'", (hk,)
    ).fetchone()[0] == 1

    sal = conn.execute(
        "SELECT salary_min, salary_max, currency FROM s_job_salary WHERE hk_job=?", (hk,)
    ).fetchone()
    assert sal is not None and sal[0] == 8.0 and sal[1] == 12.0 and sal[2] == "INR"

    meta = conn.execute("SELECT work_mode, level FROM s_job_meta WHERE hk_job=?", (hk,)).fetchone()
    assert meta[0] == "remote" and meta[1] == "senior"

    names = {r[0] for r in conn.execute("SELECT skill_name FROM h_skill")}
    assert "PYTHON" in names and "SQL" in names and "POWER BI" in names
    assert conn.execute("SELECT COUNT(*) FROM l_job_skill WHERE hk_job=?", (hk,)).fetchone()[0] == 3
    conn.close()


def test_unchanged_record_no_duplicate():
    conn = load_dv.open_db()
    rec = _rec("2", "Data Analyst")
    hk = load_dv.md5_key("test_src", "2")
    stats = {"new": 0, "changed": 0, "unchanged": 0, "closed": 0}
    load_dv.load_record(conn, rec, _stamp(), stats)
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM s_job WHERE hk_job=?", (hk,)).fetchone()[0] == 1

    # Same details again (new timestamp) -> unchanged, NO new rows/events for this job.
    stats2 = {"new": 0, "changed": 0, "unchanged": 0, "closed": 0}
    load_dv.load_record(conn, rec, _stamp(), stats2)
    conn.commit()
    assert stats2["unchanged"] == 1
    assert conn.execute("SELECT COUNT(*) FROM s_job WHERE hk_job=?", (hk,)).fetchone()[0] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM change_log WHERE hk_job=?", (hk,)
    ).fetchone()[0] == 1  # only the NEW
    conn.close()