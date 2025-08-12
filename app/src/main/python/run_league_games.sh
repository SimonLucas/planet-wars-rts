#!/usr/bin/env bash
set -euo pipefail
N=${1:-5}

for i in $(seq "$N"); do
  echo "Run $i"
  SECONDS=0
  python3 -m league.run_agents_from_db
  echo "Elapsed: ${SECONDS}s"
done
