"""Send the daily batch summary to Abhinav's Telegram DM (Friday bot).

Runs at the end of each batch. Reads TELEGRAM_BOT_TOKEN from ~/.hermes/.env,
queries today's change_log + open-job count, and sends a short summary via
the Telegram Bot API directly (no gateway needed).
"""
import os
import sqlite3
import sys
from datetime import date
from pathlib import Path

import requests

BASE = Path(__file__).parent
DB = BASE / "jobvault.db"
CHAT_ID = "1287052783"


def load_token():
    env_path = Path.home() / ".hermes" / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def main():
    token = load_token()
    if not token:
        print("telegram: TELEGRAM_BOT_TOKEN not found in ~/.hermes/.env")
        return

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    today = date.today().isoformat()

    open_count = conn.execute(
        "SELECT COUNT(*) AS n FROM v_job_current WHERE status='open'").fetchone()["n"]
    by_type = {r["change_type"]: r["n"] for r in conn.execute(
        "SELECT change_type, COUNT(*) AS n FROM change_log WHERE batch_date=? GROUP BY change_type",
        (today,))}
    conn.close()

    msg = (
        f"📊 JobVault batch {today}\n"
        f"Open jobs: {open_count}\n"
        f"New: {by_type.get('NEW', 0)} | Changed: {by_type.get('UPDATED', 0)} | Closed: {by_type.get('CLOSED', 0)}"
    )

    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg},
        timeout=20,
    )
    data = r.json()
    if data.get("ok"):
        print("telegram: summary sent")
    else:
        print(f"telegram: FAILED - {data.get('description')}")


if __name__ == "__main__":
    main()