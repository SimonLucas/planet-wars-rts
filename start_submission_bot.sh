#!/usr/bin/env bash
set -euo pipefail

SESSION_NAME="submission-bot"

# Check if the session already exists
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "⚠️  Session '$SESSION_NAME' already exists."
    echo "To view it: tmux attach -t $SESSION_NAME"
    echo "To kill it: tmux kill-session -t $SESSION_NAME"
    exit 1
fi

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Create new detached session and run the submission bot
echo "🚀 Starting submission bot in tmux session '$SESSION_NAME'"
tmux new-session -d -s "$SESSION_NAME" -c "$SCRIPT_DIR" "./run_submission_bot.sh"

echo "✅ Submission bot started successfully!"
echo ""
echo "Useful commands:"
echo "  View the bot:   tmux attach -t $SESSION_NAME"
echo "  Detach:         Ctrl+B then D"
echo "  Stop the bot:   tmux kill-session -t $SESSION_NAME"
