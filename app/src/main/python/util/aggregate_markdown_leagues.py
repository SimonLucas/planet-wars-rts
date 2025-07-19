import os
import re
from collections import defaultdict
from pathlib import Path

# Define the path where the league_N.md files are stored
INPUT_DIR = Path("/tmp/simonl-planetwars-run")  # ← Change this to your directory

# Data structure to hold aggregated results
agent_stats = defaultdict(lambda: {"wins": 0.0, "games": 0})

# Match lines like: | 2 | FlexibleEvoAgent... | 75.5 | 200 |
line_pattern = re.compile(r"\|\s*\d+\s*\|\s*(.+?)\s*\|\s*([\d.]+)\s*\|\s*(\d+)\s*\|")

# Process each markdown file
for file in INPUT_DIR.glob("league_*.md"):
    with open(file, "r", encoding="utf-8") as f:
        for line in f:
            match = line_pattern.match(line)
            if match:
                name = match.group(1).strip()
                win_rate = float(match.group(2))
                played = int(match.group(3))
                agent_stats[name]["wins"] += win_rate * played / 100
                agent_stats[name]["games"] += played

# Compute aggregated win rate and sort
aggregate_results = []
for name, stats in agent_stats.items():
    total_wins = stats["wins"]
    total_games = stats["games"]
    avg_win_rate = 100 * total_wins / total_games if total_games > 0 else 0
    aggregate_results.append((name, avg_win_rate, total_games))

# Sort by average win rate descending
aggregate_results.sort(key=lambda x: x[1], reverse=True)

# Output as Markdown
print("| Rank | Agent Name | Avg Win Rate % | Total Played |")
print("|------|------------|----------------|---------------|")
for i, (name, avg_win_rate, total_games) in enumerate(aggregate_results, start=1):
    print(f"| {i} | {name} | {avg_win_rate:.1f} | {total_games} |")
