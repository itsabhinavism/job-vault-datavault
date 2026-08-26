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
# Push the freshly exported CSVs to GitHub so they stay current + downloadable.
GIT_ASKPASS=~/.hermes/scripts/git_askpass.sh
export GIT_ASKPASS
git add export/
if git diff --cached --quiet; then
  echo "export: no changes to commit"
else
  git commit -m "data: refresh export CSVs $(date +%F)" >/dev/null && \
  git push origin main >> "$LOG" 2>&1 && echo "export: pushed CSVs to GitHub" \
  || echo "export: commit/push failed (see log)"
fi
echo "=== Batch finished ==="