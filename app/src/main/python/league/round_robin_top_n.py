#!/usr/bin/env python3
"""
Generate a round-robin win-rate table for the top-N agents in a league.

Run as:
    python -m league.round_robin_top_n
    python -m league.round_robin_top_n --top-n 5 --league 5 --out results/round_robin.md
    python -m league.round_robin_top_n --no-distinct   # allow multiple agents per family
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from league.init_db import get_default_db_path
from league.league_schema import Agent, League, Match, Rating
from league.run_agents_from_db import LEAGUE_ID


def extract_family(name: str) -> str:
    """
    Collapse agent variants (different commits / hyperparameter sweeps) to a
    shared family label so that only the best representative is selected.

      1. Strip 7-8 char hex commit suffix   nanaboshi08271-5ea4531 → nanaboshi08271
      2. Strip trailing run digits (3+)     nanaboshi08271         → nanaboshi
      3. Strip trailing punctuation         gnn_                   → gnn
      4. Take prefix up to first underscore gnn_cont999_128_top64  → gnn
    """
    s = re.sub(r'-[0-9a-f]{7,8}$', '', name)
    s = re.sub(r'\d{3,}$', '', s)
    s = s.rstrip('-_')
    if '_' in s:
        s = s.split('_')[0]
    return s


def fetch_top_agents(
    session: Session,
    league_id: int,
    top_n: int,
    distinct: bool = True,
) -> list[dict]:
    """
    Return top-N agents ranked by conservative rating (μ − 3σ).
    When distinct=True, at most one agent per family is included (the best one).
    """
    rows = (
        session.query(Rating, Agent)
        .join(Agent, Rating.agent_id == Agent.agent_id)
        .filter(Rating.league_id == league_id)
        .all()
    )
    ranked = sorted(rows, key=lambda ra: ra[0].mu - 3.0 * ra[0].sigma, reverse=True)

    results: list[dict] = []
    seen_families: set[str] = set()

    for r, a in ranked:
        family = extract_family(a.name)
        if distinct and family in seen_families:
            continue
        seen_families.add(family)
        results.append({
            "agent_id": a.agent_id,
            "name": a.name,
            "family": family,
            "mu": float(r.mu),
            "sigma": float(r.sigma),
            "conservative": float(r.mu - 3.0 * r.sigma),
        })
        if len(results) == top_n:
            break

    return results


def fetch_agents_by_name(
    session: Session,
    league_id: int,
    names: list[str],
) -> list[dict]:
    """Return agents matching the given names, ordered by conservative rating.

    Agents are looked up from the Agent table (no league dependency).
    Ratings are fetched for the specified league; agents without a rating in
    that league fall back to defaults (mu0=25, sigma0=8.333).
    """
    agents = session.query(Agent).filter(Agent.name.in_(names)).all()
    found = {a.name for a in agents}
    missing = set(names) - found
    if missing:
        raise SystemExit(f"Agents not found: {', '.join(sorted(missing))}")

    MU0, SIGMA0 = 25.0, 25.0 / 3.0
    results = []
    for a in agents:
        r = session.get(Rating, {"agent_id": a.agent_id, "league_id": league_id})
        mu = float(r.mu) if r else MU0
        sigma = float(r.sigma) if r else SIGMA0
        results.append({
            "agent_id": a.agent_id,
            "name": a.name,
            "family": extract_family(a.name),
            "mu": mu,
            "sigma": sigma,
            "conservative": mu - 3.0 * sigma,
        })

    results.sort(key=lambda x: x["conservative"], reverse=True)
    return results


def compute_head_to_head(
    session: Session,
    league_id: int,
    agent_ids: list[int],
) -> dict[tuple[int, int], tuple[int, int]]:
    """
    Returns a dict mapping (focal_id, opp_id) -> (wins, total_games).
    Only matches between the given agent_ids are considered.
    """
    id_set = set(agent_ids)
    rows = session.execute(
        select(Match.player1_id, Match.player2_id, Match.winner_id)
        .where(Match.player1_id.in_(id_set))
        .where(Match.player2_id.in_(id_set))
    ).all()

    # (focal, opp) -> [wins, games]
    counts: dict[tuple[int, int], list[int]] = {}
    for aid in agent_ids:
        for oid in agent_ids:
            if aid != oid:
                counts[(aid, oid)] = [0, 0]

    for p1, p2, winner in rows:
        if winner is None or p1 == p2:
            continue
        counts[(p1, p2)][1] += 1
        counts[(p2, p1)][1] += 1
        if winner == p1:
            counts[(p1, p2)][0] += 1
        elif winner == p2:
            counts[(p2, p1)][0] += 1

    return {k: (v[0], v[1]) for k, v in counts.items()}


def build_markdown(
    agents: list[dict],
    h2h: dict[tuple[int, int], tuple[int, int]],
    league_name: str,
) -> str:
    names = [a["name"] for a in agents]
    ids = [a["agent_id"] for a in agents]
    n = len(agents)

    lines: list[str] = []
    lines.append(f"# Round-Robin Win Rates — {league_name} (Top {n})")
    lines.append("")
    lines.append("_Cell shows **row agent's win rate** vs column agent (games played in brackets). Overall = mean of per-opponent win rates (each opponent weighted equally)._")
    lines.append("")

    # Header row: truncate long names for column headers
    def short(name: str, maxlen: int = 18) -> str:
        return name if len(name) <= maxlen else name[: maxlen - 1] + "…"

    col_headers = " | ".join(f"**{short(n_)}**" for n_ in names)
    lines.append(f"| Agent (rank↓) | {col_headers} | Overall |")
    lines.append("|---|" + "---:|" * n + "---:|")

    for i, agent in enumerate(agents):
        aid = ids[i]
        opp_win_rates: list[float] = []
        cells: list[str] = []
        for j, opp in enumerate(agents):
            oid = ids[j]
            if i == j:
                cells.append("—")
                continue
            wins, games = h2h.get((aid, oid), (0, 0))
            if games == 0:
                cells.append("n/a")
            else:
                wr = 100.0 * wins / games
                opp_win_rates.append(wr)
                cells.append(f"{wr:.1f}% ({games})")

        overall = f"{sum(opp_win_rates) / len(opp_win_rates):.1f}%" if opp_win_rates else "n/a"
        cell_str = " | ".join(cells)
        rating_str = f"{agent['conservative']:.1f}"
        lines.append(f"| **{agent['name']}** (μ−3σ={rating_str}) | {cell_str} | **{overall}** |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Agent Ratings (Top N)")
    lines.append("")
    lines.append("| Rank | Agent | μ | σ | μ − 3σ |")
    lines.append("|---:|---|---:|---:|---:|")
    for rank, a in enumerate(agents, 1):
        lines.append(f"| {rank} | {a['name']} | {a['mu']:.3f} | {a['sigma']:.3f} | {a['conservative']:.3f} |")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Round-robin win-rate table for top-N league agents.")
    ap.add_argument("--db", default=None, help="SQLAlchemy DB URL (default: league default path)")
    ap.add_argument("--league", type=int, default=LEAGUE_ID, help=f"League ID (default: {LEAGUE_ID})")
    ap.add_argument("--top-n", type=int, default=5, help="Number of top agents to include (default: 5)")
    ap.add_argument("--names", type=str, default=None, help="Comma-separated list of exact agent names to include (overrides --top-n)")
    ap.add_argument("--out", type=str, default=None, help="Output .md file path (default: stdout)")
    ap.add_argument(
        "--distinct", dest="distinct", action="store_true", default=True,
        help="One agent per family only — best representative (default: on)",
    )
    ap.add_argument(
        "--no-distinct", dest="distinct", action="store_false",
        help="Allow multiple agents from the same family",
    )
    args = ap.parse_args()

    db_url = args.db or get_default_db_path()
    engine = create_engine(db_url, future=True)

    with Session(engine) as session:
        league = session.get(League, args.league)
        league_name = league.name if league else f"League {args.league}"

        if args.names:
            name_list = [n.strip() for n in args.names.split(",") if n.strip()]
            agents = fetch_agents_by_name(session, args.league, name_list)
        else:
            agents = fetch_top_agents(session, args.league, args.top_n, distinct=args.distinct)
        if not agents:
            print("No agents found — check league ID and ratings table.")
            return

        agent_ids = [a["agent_id"] for a in agents]
        h2h = compute_head_to_head(session, args.league, agent_ids)
        md = build_markdown(agents, h2h, league_name)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md, encoding="utf-8")
        print(f"Wrote {out_path}")
    else:
        print(md)


if __name__ == "__main__":
    main()
