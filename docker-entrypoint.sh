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

# Both cron and the dashboard may request a run. Exactly one process may own
# the shared output at a time; exit 75 tells the caller that a run is active.
exec flock -n /app/output/.run.lock python main.py
