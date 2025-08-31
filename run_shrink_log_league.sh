#!/usr/bin/env bash
source .venv/bin/activate
cd app/src/main/python || exit 1
set -euo pipefail
N=${1:-5}

# --- helper: aggressively shrink logs ---
shrink_logs() {
  # Best-effort: don’t fail the loop if any of these error
  {
    # Truncate rsyslog text logs (fast + immediate)
    sudo truncate -s 0 /var/log/syslog 2>/dev/null || true
    sudo truncate -s 0 /var/log/syslog.1 2>/dev/null || true

    # Tell journald to rotate and keep only a small budget
    sudo journalctl --rotate 2>/dev/null || true
    sudo journalctl --vacuum-size=200M 2>/dev/null || true
  } || true
}

for i in $(seq "$N"); do
  echo "Run $i"
  SECONDS=0

  # pre-emptively trim logs at the start of each iteration
  shrink_logs

  python3 -m league.run_agents_uniform
  echo "Elapsed: ${SECONDS}s"

  # trim again right after the noisy step
  shrink_logs

  python -m league.league_ratings --reset --order time
  python -m league.export_leaderboard_md
  python -m league.commit_leaderboard_to_git
  python -m league.process_completed_submissions
  python -m league.launch_agents

  # and once more at the end of the loop for good measure
  shrink_logs
done
