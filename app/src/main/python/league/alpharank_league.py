#!/usr/bin/env python3
from __future__ import annotations
import argparse, math, os
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from league.league_schema import Agent, League, Match

"""
Usage:
  python -m league.alpharank_league --db sqlite://///home/simonlucas/cog-runs/new-league.db  --league-id 5  --out-dir /home/simonlucas/cog-runs/match-reports  --alpha 100.0 --mutation 1e-6

"""

@dataclass
class PairCounts:
    # For unordered pair (a,b) with a<b: wins_ab = a beats b, wins_ba = b beats a
    wins_ab: int = 0
    wins_ba: int = 0
    @property
    def games(self) -> int:
        return self.wins_ab + self.wins_ba

def safe_exp(x: float) -> float:
    return math.exp(min(50.0, x))

def load_league_data(session: Session, league_id: int):
    rows = session.execute(
        select(Match.player1_id, Match.player2_id, Match.winner_id)
        .where(Match.league_id == league_id)
    ).all()

    agent_ids = set()
    counts: Dict[Tuple[int,int], PairCounts] = defaultdict(PairCounts)

    for p1, p2, w in rows:
        if not p1 or not p2 or not w or p1 == p2:
            continue
        agent_ids.update((p1, p2))
        a, b = (p1, p2) if p1 < p2 else (p2, p1)  # unordered key with a<b
        pc = counts[(a, b)]
        if w == a:
            pc.wins_ab += 1
        elif w == b:
            pc.wins_ba += 1
        # else: ignore (shouldn't happen)

    agent_ids = sorted(agent_ids)
    id2idx = {aid: i for i, aid in enumerate(agent_ids)}
    idx2id = {i: aid for aid, i in id2idx.items()}
    names = dict(session.execute(
        select(Agent.agent_id, Agent.name).where(Agent.agent_id.in_(agent_ids))
    ).all())
    league_row = session.execute(select(League.name).where(League.league_id == league_id)).first()
    league_name = league_row[0] if league_row else f"League {league_id}"
    return agent_ids, id2idx, idx2id, names, counts, league_name

def build_winrate_matrix(agent_ids: List[int], id2idx: Dict[int,int],
                         counts: Dict[Tuple[int,int], PairCounts],
                         smoothing: float = 0.5):
    """
    p[i][j] = P(i beats j); diagonal = 0.5
    smoothing = 0.5 is Jeffreys prior -> avoids exact 0/1 when data is scarce.
    """
    n = len(agent_ids)
    p = [[0.5]*n for _ in range(n)]
    g = [[0]*n for _ in range(n)]
    w = [[0]*n for _ in range(n)]

    for (a_id, b_id), pc in counts.items():
        i, j = id2idx[a_id], id2idx[b_id]
        tot = pc.games
        if tot > 0:
            # smoothed win rates
            p_i_j = (pc.wins_ab + smoothing) / (tot + 2*smoothing)
            p_j_i = 1.0 - p_i_j
            p[i][j] = p_i_j
            p[j][i] = p_j_i
            g[i][j] = g[j][i] = tot
            w[i][j] = pc.wins_ab
            w[j][i] = pc.wins_ba
        # else leave defaults (0.5, 0 games)
    return p, g, w

def build_profile_graph(p: List[List[float]], alpha: float, mutation: float):
    n = len(p)
    profiles = [(i,j) for i in range(n) for j in range(n) if i != j]
    idx = {ij:k for k,ij in enumerate(profiles)}
    trans: List[Dict[int,float]] = []
    for (i,j) in profiles:
        base = [(idx[(i,j)], 1.0)]  # self-loop
        # row (i) deviations
        for k in range(n):
            if k==i or k==j: continue
            delta = p[k][j] - p[i][j]
            base.append((idx[(k,j)], mutation if delta <= 0 else safe_exp(alpha*delta)))
        # col (j) deviations
        for k in range(n):
            if k==j or k==i: continue
            delta = p[k][i] - p[j][i]
            base.append((idx[(i,k)], mutation if delta <= 0 else safe_exp(alpha*delta)))
        s = sum(w for _,w in base)
        row = {}
        for to, wgt in base:
            row[to] = row.get(to, 0.0) + (wgt/s)
        trans.append(row)
    return profiles, trans

def stationary_distribution(trans: List[Dict[int,float]], tol=1e-12, max_iter=20000):
    m = len(trans)
    pi = [1.0/m]*m
    for _ in range(max_iter):
        nxt = [0.0]*m
        for i,row in enumerate(trans):
            pi_i = pi[i]
            for j,pij in row.items():
                nxt[j] += pi_i*pij
        s = sum(nxt)
        if s == 0: nxt = [1.0/m]*m
        else: nxt = [x/s for x in nxt]
        if sum(abs(a-b) for a,b in zip(pi,nxt)) < tol:
            break
        pi = nxt
    return pi

def alpharank_scores(agent_ids: List[int], p: List[List[float]], alpha: float, mutation: float):
    profiles, trans = build_profile_graph(p, alpha, mutation)
    pi_profiles = stationary_distribution(trans)
    n = len(agent_ids)
    mass = [0.0]*n
    for prob, (i,j) in zip(pi_profiles, profiles):
        mass[i] += 0.5*prob
        mass[j] += 0.5*prob
    s = sum(mass)
    if s > 0: mass = [x/s for x in mass]
    return mass

def write_markdown(out_path: str, league_name: str, alpha: float, mutation: float,
                   agent_ids: List[int], names: Dict[int,str],
                   total_games: List[int], total_wins: List[int],
                   weighted_wr: List[float], mass: List[float]):
    order = sorted(range(len(agent_ids)),
                   key=lambda i: (-mass[i], -weighted_wr[i], names.get(agent_ids[i],"").lower()))
    lines = []
    lines += [f"# AlphaRank — {league_name}", "",
              f"- **alpha** = `{alpha}`  |  **mutation** = `{mutation}`",
              f"- Agents: {len(agent_ids)}", "",
              "| Rank | Agent | AlphaRank Mass % | Total Games | Wins | Weighted Win % |",
              "|---:|---|---:|---:|---:|---:|"]
    for rank, i in enumerate(order, 1):
        aid = agent_ids[i]
        nm = names.get(aid, f"Agent {aid}")
        lines.append(f"| {rank} | {nm} | {100.0*mass[i]:.2f} | {total_games[i]} | {total_wins[i]} | {100.0*weighted_wr[i]:.1f} |")
    lines += ["",
              "> Notes: pairwise win rates use an unordered aggregation with Jeffreys prior (0.5).",
              "> Missing pairs default to 0.5; totals are symmetric across each pair.", ""]
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--league-id", type=int, required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--alpha", type=float, default=100.0)
    ap.add_argument("--mutation", type=float, default=1e-6)
    ap.add_argument("--smoothing", type=float, default=0.5, help="Jeffreys prior; set 0 to disable")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    engine = create_engine(args.db, future=True)
    with Session(engine) as session:
        agent_ids, id2idx, idx2id, names, counts, league_name = load_league_data(session, args.league_id)
        if len(agent_ids) < 2:
            out = os.path.join(args.out_dir, "alpharank.md")
            with open(out, "w", encoding="utf-8") as f: f.write(f"# AlphaRank — {league_name}\n\nNot enough agents.\n")
            print(f"✅ Wrote {out}"); return

        p, g, w = build_winrate_matrix(agent_ids, id2idx, counts, smoothing=args.smoothing)

        n = len(agent_ids)
        total_games = [0]*n
        total_wins  = [0]*n
        for i in range(n):
            for j in range(n):
                if i==j: continue
                total_games[i] += g[i][j]
                total_wins[i]  += w[i][j]
        weighted_wr = [(total_wins[i]/total_games[i]) if total_games[i]>0 else 0.0 for i in range(n)]

        mass = alpharank_scores(agent_ids, p, alpha=args.alpha, mutation=args.mutation)

        out_md = os.path.join(args.out_dir, "alpharank.md")
        write_markdown(out_md, league_name, args.alpha, args.mutation,
                       agent_ids, names, total_games, total_wins, weighted_wr, mass)
        print(f"✅ AlphaRank computed for {len(agent_ids)} agents. Wrote: {out_md}")

if __name__ == "__main__":
    main()
