#!/usr/bin/env python3

"""
run as:

python -m league.compute_agent_matchups --db sqlite:////home/simonlucas/cog-runs/new-league.db --league-id 5 --out-dir /home/simonlucas/cog-runs/match-reports

"""

from __future__ import annotations

import argparse
import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Tuple, List

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

# Adjust import path if needed
from league.league_schema import Agent, Match, League


@dataclass
class PairStat:
    games: int = 0
    wins: int = 0        # total wins (seat-agnostic) for focal agent vs this opponent
    wins_p1: int = 0     # wins when focal agent sat as Player 1
    wins_p2: int = 0     # wins when focal agent sat as Player 2


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
    for p1, p2, _ in rows:
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

        # Perspective of player1 (focal = p1)
        ps = stats[p1][p2]
        ps.games += 1
        if w == p1:
            ps.wins += 1
            ps.wins_p1 += 1

        # Perspective of player2 (focal = p2)
        qs = stats[p2][p1]
        qs.games += 1
        if w == p2:
            qs.wins += 1
            qs.wins_p2 += 1

    return stats, agent_names, league_name


def build_agent_rows(agent_id: int, stats: Dict[int, Dict[int, PairStat]], agent_names: Dict[int, str]):
    """
    Returns:
      rows: List[Tuple[opponent_name, wins_p1, wins_p2, wins_total, games, win_rate_pct]]
      totals: (total_wins, total_games, total_wins_p1, total_wins_p2)
      unweighted_avg: float
      weighted_avg: float
    """
    rows: List[Tuple[str, int, int, int, int, float]] = []
    total_wins = total_games = total_wins_p1 = total_wins_p2 = 0

    for opp_id, ps in stats.get(agent_id, {}).items():
        if opp_id == agent_id or ps.games <= 0:
            continue
        wins_total = ps.wins
        wr = 100.0 * wins_total / ps.games
        rows.append((
            agent_names.get(opp_id, f"Agent {opp_id}"),
            ps.wins_p1,
            ps.wins_p2,
            wins_total,
            ps.games,
            wr,
        ))
        total_wins += wins_total
        total_games += ps.games
        total_wins_p1 += ps.wins_p1
        total_wins_p2 += ps.wins_p2

    # Sort by Win Rate % (desc), then Games (desc), then Opponent name
    rows.sort(key=lambda r: (-r[5], -r[4], r[0].lower()))

    weighted_avg = (100.0 * total_wins / total_games) if total_games > 0 else 0.0
    unweighted_avg = (sum(r[5] for r in rows) / len(rows)) if rows else 0.0
    return rows, (total_wins, total_games, total_wins_p1, total_wins_p2), unweighted_avg, weighted_avg


def make_agent_markdown(
    agent_id: int,
    stats: Dict[int, Dict[int, PairStat]],
    agent_names: Dict[int, str],
    league_name: str,
) -> str:
    name = agent_names.get(agent_id, f"Agent {agent_id}")
    rows, (total_wins, total_games, total_wins_p1, total_wins_p2), unweighted_avg, weighted_avg = \
        build_agent_rows(agent_id, stats, agent_names)

    md: List[str] = []
    md.append(f"# {name} — {league_name}")
    md.append("")
    md.append("| Opponent | Wins (P1) | Wins (P2) | Wins (Total) | Games | Win Rate % |")
    md.append("|---|---:|---:|---:|---:|---:|")
    for opp_name, w1, w2, wt, games, wr in rows:
        md.append(f"| {opp_name} | {w1} | {w2} | {wt} | {games} | {wr:.1f} |")

    md.append("")
    md.append(f"**Overall Average (weighted by games): {weighted_avg:.1f}%**  —  **Total wins/games: {total_wins}/{total_games}**")
    md.append(f"**Overall Average (unweighted): {unweighted_avg:.1f}%**")
    md.append(f"_Seat split totals:_ **P1 wins:** {total_wins_p1} — **P2 wins:** {total_wins_p2}")
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

    for aid in agent_ids:
        rows, (total_wins, total_games, _, _), unweighted_avg, weighted_avg = build_agent_rows(aid, stats, agent_names)
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
        rows, (total_wins, total_games, total_wins_p1, total_wins_p2), unweighted_avg, weighted_avg = \
            build_agent_rows(aid, stats, agent_names)

        md.append(f"## {name}")
        md.append("")
        md.append("| Opponent | Wins (P1) | Wins (P2) | Wins (Total) | Games | Win Rate % |")
        md.append("|---|---:|---:|---:|---:|---:|")
        for opp_name, w1, w2, wt, games, wr in rows:
            md.append(f"| {opp_name} | {w1} | {w2} | {wt} | {games} | {wr:.1f} |")
        md.append("")
        md.append(f"**Overall Average (weighted by games): {weighted_avg:.1f}%**  —  **Total wins/games: {total_wins}/{total_games}**")
        md.append(f"**Overall Average (unweighted): {unweighted_avg:.1f}%**")
        md.append(f"_Seat split totals:_ **P1 wins:** {total_wins_p1} — **P2 wins:** {total_wins_p2}")
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

        # Per-agent pages
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

        # Combined league markdown
        combined_name = "league_matchups.md"
        combined_path = os.path.join(args.out_dir, combined_name)
        combined_md = make_combined_markdown(agent_ids, stats, agent_names, league_name, per_agent_file_lookup)
        with open(combined_path, "w", encoding="utf-8") as f:
            f.write(combined_md)

        # Index
        index_lines.insert(1, f"- [Combined league view](./{combined_name})")
        with open(os.path.join(args.out_dir, "index.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(index_lines))

        print(f"✅ Wrote {len(agent_ids)} agent files, league_matchups.md, and index.md to: {args.out_dir}")


if __name__ == "__main__":
    main()
