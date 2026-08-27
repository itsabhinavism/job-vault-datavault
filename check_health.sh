#!/bin/bash
for f in current_jobs job_history jobs_by_day changes skills salary_data jobs_by_mode; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "https://raw.githubusercontent.com/itsabhinavism/job-vault-datavault/main/export/${f}.csv")
  echo "$f.csv -> $code"
done
echo "---CI---"
TOKEN=$(python3 -c "import yaml;print(yaml.safe_load(open('/Users/abhinav/.hermes/config.yaml'))['github_token'])")
curl -s -H "Authorization: Bearer $TOKEN" "https://api.github.com/repos/itsabhinavism/job-vault-datavault/actions/runs?per_page=1" | python3 -c "import json,sys; r=json.load(sys.stdin)['workflow_runs'][0]; print('run:', r['display_title'][:50], '| status:', r['status'], '| conclusion:', r['conclusion'])"