#!/bin/bash
# One daily batch: scrape -> normalize -> load history -> export for Sheets.
# Log output so we can see what happened each day.
cd "$(dirname "$0")"
LOG="batch_$(date +%F).log"
exec > >(tee -a "$LOG") 2>&1

echo "=== Batch $(date '+%Y-%m-%d %H:%M:%S %Z') ==="
env -u PYTHONPATH .venv/bin/python scrape_all.py || exit 1
echo ""
env -u PYTHONPATH .venv/bin/python normalize.py || exit 1
echo ""
env -u PYTHONPATH .venv/bin/python load_dv.py || exit 1
echo ""
env -u PYTHONPATH .venv/bin/python export.py || exit 1
echo ""
echo "=== Batch finished ==="