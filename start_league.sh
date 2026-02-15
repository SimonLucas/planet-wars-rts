#!/usr/bin/env bash
set -euo pipefail

SESSION_NAME="league"

# Check if the session already exists
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "⚠️  Session '$SESSION_NAME' already exists."
    echo "To view it: tmux attach -t $SESSION_NAME"
    echo "To kill it: tmux kill-session -t $SESSION_NAME"
    exit 1
fi

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Get the number of runs (default: 5)
N=${1:-5}

# Create new detached session and run the league script
echo "🚀 Starting league (N=$N runs) in tmux session '$SESSION_NAME'"
tmux new-session -d -s "$SESSION_NAME" -c "$SCRIPT_DIR" "./run_shrink_log_league.sh $N"

echo "✅ League started successfully!"
echo ""
echo "Useful commands:"
echo "  View the league: tmux attach -t $SESSION_NAME"
echo "  Detach:          Ctrl+B then D"
echo "  Stop the league: tmux kill-session -t $SESSION_NAME"
