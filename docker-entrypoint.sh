#!/bin/sh
set -eu

# GH_TOKEN is injected only at runtime from the root-owned VPS environment
# file. Git sees it through its temporary, container-local credential store.
if [ -n "${GH_TOKEN:-}" ]; then
  git config --global credential.helper store
  printf 'https://x-access-token:%s@github.com\n' "$GH_TOKEN" > "$HOME/.git-credentials"
fi

git config --global user.name "Karol"
git config --global user.email "ogelslamovuk@users.noreply.github.com"

# Both cron and the dashboard may request a run. The lock remains held until
# the compact, non-secret result record is written as well.
export CL_RUN_STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
exec flock -n /app/output/.run.lock sh -c '
  set +e
  python main.py
  exit_code=$?
  python -m src.run_history "$CL_RUN_STARTED_AT" "$exit_code"
  exit "$exit_code"
'
