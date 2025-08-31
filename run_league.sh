#!/usr/bin/env bash
source .venv/bin/activate
cd app/src/main/python || exit 1
set -euo pipefail
N=${1:-5}

for i in $(seq "$N"); do
  echo "Run $i"
  SECONDS=0
  python3 -m league.run_agents_uniform
  echo "Elapsed: ${SECONDS}s"
  python -m league.league_ratings --reset --order time
  python -m league.export_leaderboard_md
  python -m league.commit_leaderboard_to_git
  python -m league.process_completed_submissions
  python -m league.launch_agents

done
