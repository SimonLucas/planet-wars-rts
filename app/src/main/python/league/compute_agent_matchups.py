#!/usr/bin/env python3
"""
Compute per-agent head-to-head win rates (with wins) for a given league and emit Markdown reports.

Outputs:
- One Markdown file per agent (with Wins, Games, Win Rate %)
- A combined league Markdown with:
    * a summary table (per agent totals + weighted/unweighted averages)
    * all per-agent head-to-head tables

Usage:
  python compute_agent_matchups.py \
      --db sqlite://///home/simonlucas/cog-runs/new-league.db \
      --league-id 5 \
      --out-dir /home/simonlucas/cog-runs/agent-matchups
"""
from __future__ import annotations

import argparse
import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Tuple, List

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

# Import your ORM models; adjust if your path differs
try:
    from league.league_schema import Agent, Match, League
except Exception as e:
    print("❌ Could not import league schema (league.league_schema). Adjust the import to your path.")
    raise

@dataclass
class PairStat:
    games: int = 0
    wins: int = 0  # wins for focal agent vs this opponent


def slugify(text: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in text).strip("-")


def compute_stats(session: Session, league_id: int):
    """
    Returns:
      stats: Dict[agent_id, Dict[opponent_id, PairStat]]
      agent_names: Dict[agent_id, str]
      league_name: str
    """
    rows = session.execute(
        select(Match.player1_id, Match.player2_id, Match.winner_id)
        .where(Match.league_id == league_id)
    ).all()

    agent_ids_in_league = set()
    for p1, p2, w in rows:
        agent_ids_in_league.add(p1)
        agent_ids_in_league.add(p2)

    agent_names = dict(session.execute(
        select(Agent.agent_id, Agent.name).where(Agent.agent_id.in_(agent_ids_in_league))
    ).all())

    league_row = session.execute(
        select(League.name).where(League.league_id == league_id)
    ).first()
    league_name = league_row[0] if league_row else f"League {league_id}"

    stats: Dict[int, Dict[int, PairStat]] = defaultdict(lambda: defaultdict(PairStat))
    for p1, p2, w in rows:
        if w is None:
            continue
        if p1 == p2:
            continue  # skip accidental self-plays

        # perspective of player1
        a = stats[p1][p2]
        a.games += 1
        if w == p1:
            a.wins += 1

        # perspective of player2
        b = stats[p2][p1]
        b.games += 1
        if w == p2:
            b.wins += 1

    return stats, agent_names, league_name


def build_agent_rows(agent_id: int, stats: Dict[int, Dict[int, PairStat]], agent_names: Dict[int, str]):
    """
    Returns:
      rows: List[Tuple[opponent_name, wins, games, win_rate_pct]]
      totals: (total_wins, total_games)
      unweighted_avg: float
      weighted_avg: float
    """
    rows: List[Tuple[str, int, int, float]] = []
    total_wins = 0
    total_games = 0

    for opp_id, ps in stats.get(agent_id, {}).items():
        if opp_id == agent_id or ps.games <= 0:
            continue
        wr = 100.0 * ps.wins / ps.games
        rows.append((agent_names.get(opp_id, f"Agent {opp_id}"), ps.wins, ps.games, wr))
        total_wins += ps.wins
        total_games += ps.games

    # Sort by games desc, then opponent name
    rows.sort(key=lambda r: (-r[2], r[0].lower()))

    weighted_avg = (100.0 * total_wins / total_games) if total_games > 0 else 0.0
    unweighted_avg = (sum(r[3] for r in rows) / len(rows)) if rows else 0.0
    return rows, (total_wins, total_games), unweighted_avg, weighted_avg


def make_agent_markdown(
    agent_id: int,
    stats: Dict[int, Dict[int, PairStat]],
    agent_names: Dict[int, str],
    league_name: str,
) -> str:
    name = agent_names.get(agent_id, f"Agent {agent_id}")
    rows, (total_wins, total_games), unweighted_avg, weighted_avg = build_agent_rows(agent_id, stats, agent_names)

    md: List[str] = []
    md.append(f"# {name} — {league_name}")
    md.append("")
    md.append("| Opponent | Wins | Games Played | Win Rate % |")
    md.append("|---|---:|---:|---:|")
    for opp_name, wins, games, wr in rows:
        md.append(f"| {opp_name} | {wins} | {games} | {wr:.1f} |")

    md.append("")
    md.append(f"**Overall Average (weighted by games): {weighted_avg:.1f}%**  —  **Total wins/games: {total_wins}/{total_games}**")
    md.append(f"**Overall Average (unweighted): {unweighted_avg:.1f}%**")
    md.append("")
    md.append(f"AVG={weighted_avg:.1f}")
    md.append("")
    return "\n".join(md)


def make_combined_markdown(
    agent_ids: List[int],
    stats: Dict[int, Dict[int, PairStat]],
    agent_names: Dict[int, str],
    league_name: str,
    per_agent_file_lookup: Dict[int, str],
) -> str:
    """Create a single league-wide Markdown file."""
    # Build summary rows
    summary_rows: List[Tuple[str, int, int, float, float, str]] = []
    # (agent_name, total_wins, total_games, weighted_avg, unweighted_avg, link)

    for aid in agent_ids:
        rows, (total_wins, total_games), unweighted_avg, weighted_avg = build_agent_rows(aid, stats, agent_names)
        name = agent_names.get(aid, f"Agent {aid}")
        link = per_agent_file_lookup.get(aid, "")
        summary_rows.append((name, total_wins, total_games, weighted_avg, unweighted_avg, link))

    # Sort summary by weighted avg desc, then total games desc
    summary_rows.sort(key=lambda r: (-r[3], -r[2], r[0].lower()))

    md: List[str] = []
    md.append(f"# Agent Matchups — {league_name}")
    md.append("")
    md.append("## Summary (per agent)")
    md.append("")
    md.append("| Agent | Total Wins | Total Games | Weighted Win % | Unweighted Win % |")
    md.append("|---|---:|---:|---:|---:|")
    for name, tw, tg, wavg, uavg, link in summary_rows:
        display = f"[{name}]({link})" if link else name
        md.append(f"| {display} | {tw} | {tg} | {wavg:.1f} | {uavg:.1f} |")

    # Full sections per agent
    md.append("")
    md.append("---")
    md.append("")
    for aid in agent_ids:
        name = agent_names.get(aid, f"Agent {aid}")
        rows, (total_wins, total_games), unweighted_avg, weighted_avg = build_agent_rows(aid, stats, agent_names)

        md.append(f"## {name}")
        md.append("")
        md.append("| Opponent | Wins | Games Played | Win Rate % |")
        md.append("|---|---:|---:|---:|")
        for opp_name, wins, games, wr in rows:
            md.append(f"| {opp_name} | {wins} | {games} | {wr:.1f} |")
        md.append("")
        md.append(f"**Overall Average (weighted by games): {weighted_avg:.1f}%**  —  **Total wins/games: {total_wins}/{total_games}**")
        md.append(f"**Overall Average (unweighted): {unweighted_avg:.1f}%**")
        md.append("")
        md.append("---")
        md.append("")

    return "\n".join(md)


def main():
    ap = argparse.ArgumentParser(description="Compute per-agent matchup tables for a league and write Markdown files.")
    ap.add_argument("--db", required=True, help="SQLAlchemy DB URL (e.g., sqlite:////path/to/league.db)")
    ap.add_argument("--league-id", type=int, required=True, help="League ID to filter matches")
    ap.add_argument("--out-dir", required=True, help="Directory to write Markdown files")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    engine = create_engine(args.db, future=True)
    with Session(engine) as session:
        stats, agent_names, league_name = compute_stats(session, args.league_id)
        agent_ids = sorted(agent_names.keys(), key=lambda aid: agent_names.get(aid, "").lower())

        # Write per-agent pages + index
        index_lines = [f"# Agent Matchups — {league_name}", ""]
        per_agent_file_lookup: Dict[int, str] = {}

        for aid in agent_ids:
            md = make_agent_markdown(aid, stats, agent_names, league_name)
            fname = f"{slugify(agent_names.get(aid, f'agent-{aid}'))}--agent-{aid}.md"
            fpath = os.path.join(args.out_dir, fname)
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(md)
            per_agent_file_lookup[aid] = fname
            index_lines.append(f"- [{agent_names.get(aid, f'Agent {aid}')}](./{fname})")

        # Write combined league markdown
        combined_name = "league_matchups.md"
        combined_path = os.path.join(args.out_dir, combined_name)
        combined_md = make_combined_markdown(agent_ids, stats, agent_names, league_name, per_agent_file_lookup)
        with open(combined_path, "w", encoding="utf-8") as f:
            f.write(combined_md)

        # Write index
        index_lines.insert(1, f"- [Combined league view](./{combined_name})")
        with open(os.path.join(args.out_dir, "index.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(index_lines))

        print(f"✅ Wrote {len(agent_ids)} agent files, league_matchups.md, and index.md to: {args.out_dir}")


if __name__ == "__main__":
    main()


