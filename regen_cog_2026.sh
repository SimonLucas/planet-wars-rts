#!/usr/bin/env bash
# Export the 10-agent round robin. Metang is the default representative;
# pass --variant metagross to generate the alternative table.
# Defaults to league 5. No stored results are removed by filtering.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$SCRIPT_DIR/app/src/main/python${PYTHONPATH:+:$PYTHONPATH}"
"$SCRIPT_DIR/.venv/bin/python3" -m league.export_cog_results "$@"
