from __future__ import annotations
import math
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Tuple, List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from league.league_schema import League, Match, Rating

# ---- weights (sane defaults) ----
W_SIGMA = 0.6      # how much we prioritize uncertain agents
W_UCB   = 1.0      # underplayed boost
W_STALE = 0.1      # hasn't played in a while
W_Q     = 0.7      # pair match quality
W_SUMS  = 0.3      # (σ_i + σ_j) boost
W_REPEAT= 0.2      # penalty for repeated pair
W_MU = 0.5      # how much we prioritize high μ (rating)

P_EXPLOIT = 0.25   # chance to restrict opponent search to top-K by μ
TOP_K = 8

@dataclass
class AgentStat:
    agent_id: int
    mu: float
    sigma: float
    played: int
    last_played: datetime | None

def _match_quality(mu1: float, s1: float, mu2: float, s2: float, beta: float) -> float:
    c2 = 2 * (beta ** 2) + s1 * s1 + s2 * s2
    if c2 <= 0:
        return 0.0
    dmu = mu1 - mu2
    return math.exp(- (dmu * dmu) / (2.0 * c2))

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _normalize_days(dt: datetime | None) -> float:
    if not dt:
        return 1.0
    delta = _now_utc() - (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))
    return min(delta.total_seconds() / (24*3600*7), 1.5)  # ~0..1.5 weeks

def load_stats(session: Session, league_id: int) -> tuple[Dict[int, AgentStat], int, float]:
    """Return per-agent stats, total matches T, and league beta."""
    league = session.get(League, league_id)
    s = dict(league.settings or {})
    beta = float(s.get("beta", 25.0/6.0))

    # ratings
    ratings: list[Rating] = (
        session.query(Rating)
        .filter(Rating.league_id == league_id)
        .all()
    )
    if not ratings:
        return {}, 0, beta

    # games played per agent (include all matches)
    gp_rows = (
        session.query(Match.player1_id.label("aid"), func.count().label("cnt"))
        .filter(Match.league_id == league_id)
        .group_by(Match.player1_id)
        .all()
    ) + (
        session.query(Match.player2_id.label("aid"), func.count().label("cnt"))
        .filter(Match.league_id == league_id)
        .group_by(Match.player2_id)
        .all()
    )
    played: Dict[int, int] = {}
    for aid, cnt in gp_rows:
        played[aid] = played.get(aid, 0) + int(cnt)

    # last played per agent (include all matches)
    last1 = (
        session.query(Match.player1_id.label("aid"), func.max(Match.finished_at))
        .filter(Match.league_id == league_id)
        .group_by(Match.player1_id)
        .all()
    )
    last2 = (
        session.query(Match.player2_id.label("aid"), func.max(Match.finished_at))
        .filter(Match.league_id == league_id)
        .group_by(Match.player2_id)
        .all()
    )
    last_played: Dict[int, datetime | None] = {}
    for aid, dt in last1 + last2:
        cur = last_played.get(aid)
        last_played[aid] = dt if (cur is None or (dt and dt > cur)) else cur

    # total match count (include draws)
    T = session.query(func.count()).select_from(Match)\
        .filter(Match.league_id == league_id).scalar() or 0

    stats: Dict[int, AgentStat] = {
        r.agent_id: AgentStat(
            agent_id=r.agent_id,
            mu=float(r.mu),
            sigma=float(r.sigma),
            played=int(played.get(r.agent_id, 0)),
            last_played=last_played.get(r.agent_id),
        )
        for r in ratings
    }
    return stats, int(T), beta

def load_pair_counts(session: Session, league_id: int) -> Dict[tuple[int, int], int]:
    """How often each unordered pair has met (include draws)."""
    rows = (
        session.query(Match.player1_id, Match.player2_id, func.count().label("cnt"))
        .filter(Match.league_id == league_id)
        .group_by(Match.player1_id, Match.player2_id)
        .all()
    )
    pc: Dict[tuple[int, int], int] = {}
    for a, b, c in rows:
        key = (a, b) if a < b else (b, a)
        pc[key] = pc.get(key, 0) + int(c)
    return pc

def choose_next_pair(session: Session, league_id: int = 1) -> tuple[int, int] | None:
    """Return (agent_id_a, agent_id_b) for the next match."""
    stats, T, beta = load_stats(session, league_id)
    if len(stats) < 2:
        return None

    pair_counts = load_pair_counts(session, league_id)

    # 1) Pick focal agent i by priority
    def priority(s: AgentStat) -> float:
        # balance between exploitation - mean rating (mu) and exploration -
        # more weight to those with fewer games played (played)
        ucb = math.sqrt(math.log(T + 1.0) / (s.played + 1.0))
        return W_MU * s.mu + W_UCB * ucb

    agents_sorted = sorted(stats.values(), key=priority, reverse=True)
    i: AgentStat = agents_sorted[0]

    # 2) Choose candidate opponents
    all_candidates = [s for s in stats.values() if s.agent_id != i.agent_id]
    if random.random() < P_EXPLOIT:
        topk = sorted(all_candidates, key=lambda s: s.mu, reverse=True)[:min(TOP_K, len(all_candidates))]
        candidates = topk
    else:
        candidates = all_candidates

    # 3) Score candidate j against i
    def pair_score(j: AgentStat) -> float:
        q = _match_quality(i.mu, i.sigma, j.mu, j.sigma, beta)
        repeats = pair_counts.get((min(i.agent_id, j.agent_id), max(i.agent_id, j.agent_id)), 0)
        return W_Q * q + W_SUMS * (i.sigma + j.sigma) - W_REPEAT * repeats

    j: AgentStat = max(candidates, key=pair_score)
    return (i.agent_id, j.agent_id)
