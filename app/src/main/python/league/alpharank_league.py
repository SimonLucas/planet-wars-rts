#!/usr/bin/env python3
"""
AlphaRank for Planet Wars (2-player symmetric meta-game).

- Extracts matches for a given league_id from the SQLAlchemy schema.
- Estimates win rates p[i,j] = P(agent i beats agent j) from historical matches.
- Builds an AlphaRank Markov chain over profiles (i,j), i != j.
- Computes the stationary distribution by power iteration.
- Aggregates profile mass per agent to yield AlphaRank scores.
- Outputs a Markdown file with the ranking and some sanity stats.

Assumptions:
- Two-player, constant-sum; winner_id is always set (no draws in DB).
- If a pair never played, we use p=0.5 (agnostic) to avoid disconnects.
- This is a light-weight AlphaRank implementation for symmetric games.

Usage:
  python -m league.alpharank_league \
    --db sqlite://///home/simonlucas/cog-runs/new-league.db \
    --league-id 5 \
    --out-dir /home/simonlucas/cog-runs/agent-matchups \
    --alpha 100.0 \
    --mutation 1e-6
"""
from __future__ import annotations

import argparse
import math
import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

# Adjust if your import path differs
from league.league_schema import Agent, League, Match


@dataclass
class PairCounts:
    wins_ij: int = 0  # i beats j
    wins_ji: int = 0  # j beats i

    @property
    def games(self) -> int:
        return self.wins_ij + self.wins_ji

    def p_ij(self) -> float:
        # If no games, return neutral 0.5 so the chain stays connected.
        g = self.games
        return (self.wins_ij / g) if g > 0 else 0.5


def safe_exp(x: float) -> float:
    # Cap exponent to avoid overflow for large alpha * delta
    return math.exp(min(50.0, x))


def load_league_data(session: Session, league_id: int):
    """Return (agent_ids, agent_names, counts) for the league."""
    rows = session.execute(
        select(
            Match.player1_id,
            Match.player2_id,
            Match.winner_id,
        ).where(Match.league_id == league_id)
    ).all()

    agent_ids = set()
    counts: Dict[Tuple[int, int], PairCounts] = defaultdict(PairCounts)

    for p1, p2, w in rows:
        if p1 is None or p2 is None or w is None or p1 == p2:
            continue
        agent_ids.add(p1)
        agent_ids.add(p2)
        if w == p1:
            counts[(p1, p2)].wins_ij += 1
        elif w == p2:
            counts[(p2, p1)].wins_ij += 1

    agent_ids = sorted(agent_ids)
    id2idx = {aid: i for i, aid in enumerate(agent_ids)}
    idx2id = {i: aid for aid, i in id2idx.items()}

    # names
    names = dict(
        session.execute(
            select(Agent.agent_id, Agent.name).where(Agent.agent_id.in_(agent_ids))
        ).all()
    )

    # league name (nice header)
    league_row = session.execute(
        select(League.name).where(League.league_id == league_id)
    ).first()
    league_name = league_row[0] if league_row else f"League {league_id}"

    return agent_ids, id2idx, idx2id, names, counts, league_name


def build_winrate_matrix(agent_ids: List[int], id2idx: Dict[int, int], counts: Dict[Tuple[int, int], PairCounts]):
    """Return p[i][j] = P(i beats j). Diagonal set to 0.5."""
    n = len(agent_ids)
    p = [[0.5 for _ in range(n)] for _ in range(n)]
    g = [[0 for _ in range(n)] for _ in range(n)]
    w = [[0 for _ in range(n)] for _ in range(n)]
    for (i_id, j_id), c in counts.items():
        i = id2idx[i_id]
        j = id2idx[j_id]
        p[i][j] = c.p_ij()
        g[i][j] = c.games
        w[i][j] = c.wins_ij
    # Fill the opposite direction from available counts so g is symmetric
    n_agents = range(n)
    for i in n_agents:
        for j in n_agents:
            if i == j:
                p[i][j] = 0.5
                continue
            # if one direction missing, infer the other if present
            if g[i][j] == 0 and g[j][i] > 0:
                # use games from opposite direction
                g[i][j] = g[j][i]
                # p(i beats j) = 1 - p(j beats i)
                p[i][j] = 1.0 - p[j][i]
                # wins_ij implied:
                w[i][j] = int(round(p[i][j] * g[i][j]))
    return p, g, w


def build_profile_graph(p: List[List[float]], alpha: float, mutation: float):
    """
    Build a sparse transition graph for the AlphaRank Markov chain over profiles (i,j).
    Returns:
      profiles: List[Tuple[i,j]]
      trans: List[Dict[next_index, prob]]
    """
    n = len(p)
    profiles: List[Tuple[int, int]] = [(i, j) for i in range(n) for j in range(n) if i != j]
    index_of = {ij: k for k, ij in enumerate(profiles)}

    trans: List[Dict[int, float]] = []
    for (i, j) in profiles:
        # Row (agent i) payoff vs j is p[i][j]
        # Column (agent j) payoff vs i is p[j][i] = 1 - p[i][j]
        base = []
        # self-loop ensures aperiodicity
        base.append((index_of[(i, j)], 1.0))

        # Row deviations: i -> k
        for k in range(n):
            if k == i or k == j:
                continue
            delta = p[k][j] - p[i][j]
            weight = mutation if delta <= 0 else safe_exp(alpha * delta)
            if weight > 0.0:
                base.append((index_of[(k, j)], weight))

        # Column deviations: j -> k (column payoff increases if p[k][i] - p[j][i] > 0)
        for k in range(n):
            if k == j or k == i:
                continue
            delta = p[k][i] - p[j][i]
            weight = mutation if delta <= 0 else safe_exp(alpha * delta)
            if weight > 0.0:
                base.append((index_of[(i, k)], weight))

        # Normalize
        total = sum(w for _, w in base)
        row = {}
        for idx, wgt in base:
            row[idx] = row.get(idx, 0.0) + (wgt / total)
        trans.append(row)

    return profiles, trans


def stationary_distribution(trans: List[Dict[int, float]], tol: float = 1e-12, max_iter: int = 20000):
    """
    Power iteration on a sparse row-stochastic graph.
    Returns stationary distribution pi over states.
    """
    m = len(trans)
    pi = [1.0 / m] * m  # uniform start

    for _ in range(max_iter):
        nxt = [0.0] * m
        for i, row in enumerate(trans):
            pi_i = pi[i]
            for j, p_ij in row.items():
                nxt[j] += pi_i * p_ij
        # normalize
        s = sum(nxt)
        if s == 0.0:
            # fallback to uniform (should not happen)
            nxt = [1.0 / m] * m
        else:
            inv = 1.0 / s
            nxt = [x * inv for x in nxt]

        # convergence check
        diff = sum(abs(a - b) for a, b in zip(pi, nxt))
        pi = nxt
        if diff < tol:
            break
    return pi


def alpharank_scores(agent_ids: List[int], p: List[List[float]], alpha: float, mutation: float):
    """
    Compute AlphaRank mass per agent by aggregating stationary mass over profiles.
    """
    profiles, trans = build_profile_graph(p, alpha=alpha, mutation=mutation)
    pi_profiles = stationary_distribution(trans)

    n = len(agent_ids)
    mass = [0.0] * n
    for prob, (i, j) in zip(pi_profiles, profiles):
        # symmetric aggregation: split mass between the two players in the profile
        mass[i] += prob * 0.5
        mass[j] += prob * 0.5
    # normalize to sum 1 (just in case)
    s = sum(mass)
    if s > 0:
        mass = [x / s for x in mass]
    return mass, profiles, pi_profiles


def write_markdown(
    out_path: str,
    league_name: str,
    alpha: float,
    mutation: float,
    agent_ids: List[int],
    names: Dict[int, str],
    total_games: List[int],
    total_wins: List[int],
    weighted_wr: List[float],
    mass: List[float],
):
    order = sorted(range(len(agent_ids)), key=lambda i: (-mass[i], -weighted_wr[i], names.get(agent_ids[i], "").lower()))
    lines: List[str] = []
    lines.append(f"# AlphaRank — {league_name}")
    lines.append("")
    lines.append(f"- **alpha** = `{alpha}`  |  **mutation** = `{mutation}`")
    lines.append(f"- Agents: {len(agent_ids)}")
    lines.append("")
    lines.append("| Rank | Agent | AlphaRank Mass % | Total Games | Wins | Weighted Win % |")
    lines.append("|---:|---|---:|---:|---:|---:|")
    for rank, i in enumerate(order, start=1):
        aid = agent_ids[i]
        nm = names.get(aid, f"Agent {aid}")
        lines.append(f"| {rank} | {nm} | {100.0*mass[i]:.2f} | {total_games[i]} | {total_wins[i]} | {100.0*weighted_wr[i]:.1f} |")

    lines.append("")
    lines.append("> Notes: AlphaRank mass is computed from the stationary distribution of a Markov chain over profiles (i,j). ")
    lines.append("> If two versions never faced each other, their p(i beats j) is set to 0.5 (neutral).")
    lines.append("")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="SQLAlchemy DB URL, e.g., sqlite://///path/to/league.db")
    ap.add_argument("--league-id", type=int, required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--alpha", type=float, default=100.0, help="Selection intensity (higher -> greedier best-response)")
    ap.add_argument("--mutation", type=float, default=1e-6, help="Small baseline move prob for non-improving deviations")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    engine = create_engine(args.db, future=True)
    with Session(engine) as session:
        agent_ids, id2idx, idx2id, names, counts, league_name = load_league_data(session, args.league_id)

        if len(agent_ids) < 2:
            out = os.path.join(args.out_dir, "alpharank.md")
            with open(out, "w", encoding="utf-8") as f:
                f.write(f"# AlphaRank — {league_name}\n\nNot enough agents to rank.\n")
            print(f"✅ Wrote {out}")
            return

        p, g, w = build_winrate_matrix(agent_ids, id2idx, counts)

        # Per-agent totals and weighted win rate for extra context
        n = len(agent_ids)
        total_games = [0] * n
        total_wins = [0] * n
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                total_games[i] += g[i][j]
                total_wins[i] += w[i][j]
        weighted_wr = [(total_wins[i] / total_games[i]) if total_games[i] > 0 else 0.0 for i in range(n)]

        mass, profiles, pi_profiles = alpharank_scores(agent_ids, p, alpha=args.alpha, mutation=args.mutation)

        out_md = os.path.join(args.out_dir, "alpharank.md")
        write_markdown(
            out_md, league_name, args.alpha, args.mutation,
            agent_ids, names, total_games, total_wins, weighted_wr, mass
        )

        print(f"✅ AlphaRank computed for {len(agent_ids)} agents. Wrote: {out_md}")


if __name__ == "__main__":
    main()
