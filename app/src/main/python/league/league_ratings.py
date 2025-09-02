# league_ratings.py
import argparse
import math
import os
from typing import Dict, Optional
import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from league.init_db import get_default_db_path
from league.league_schema import League, Match, Rating
from league.run_agents_from_db import LEAGUE_ID

# ---------- defaults (TrueSkill-like 1v1) ----------
# More conservative tau by default to reduce sigma drift.
TS_DEFAULTS = {
    "mu0": 25.0,
    "sigma0": 25.0 / 3.0,           # ~8.333
    "beta": 25.0 / 6.0,             # ~4.167  (≈ sigma0/2)
    "tau": (25.0 / 3.0) / 300.0,    # ~0.0278 (was ~0.083). Lower = more stable.
    "draw_probability": 0.0,        # draws ignored; schema requires a winner
    "last_processed_match_id": 0,
}

EPS = 1e-12
MIN_SIGMA_ABS = 1e-3   # hard floor for σ

# ---------- math helpers ----------
def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)

def _norm_cdf(x: float) -> float:
    # numerically safer CDF (clamped)
    v = 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
    return min(max(v, EPS), 1.0 - EPS)

def _v_exceeds(t: float) -> float:
    cdf = _norm_cdf(t)
    return _norm_pdf(t) / cdf

def _w_exceeds(t: float) -> float:
    v = _v_exceeds(t)
    return v * (v + t)

def _v_exceeds_neg(t: float) -> float:
    cdf_tail = 1.0 - _norm_cdf(t)
    return _norm_pdf(t) / max(cdf_tail, EPS)

def _w_exceeds_neg(t: float) -> float:
    v = _v_exceeds_neg(t)
    return v * (v - t)

# ---------- league + ratings primitives ----------
def ensure_league(session: Session,
                  league_id: int = 1,
                  name: str = "Remote League",
                  description: str = "Auto-created league for remote pair runs",
                  settings_overrides: Optional[Dict] = None,
                  persist_overrides: bool = False) -> League:
    """Get or create a league row with sane TS defaults; patch missing keys.
       If persist_overrides=True, store overrides in league.settings.
    """
    league = session.get(League, league_id)
    if league is None:
        league = League(
            league_id=league_id,
            name=name,
            description=description,
            settings={**TS_DEFAULTS, **(settings_overrides or {})},
        )
        session.add(league)
        session.commit()
    else:
        s = dict(league.settings or {})
        changed = False
        # fill missing defaults
        for k, v in TS_DEFAULTS.items():
            if k not in s:
                s[k] = v
                changed = True
        # optionally apply overrides
        if settings_overrides and persist_overrides:
            for k, v in settings_overrides.items():
                if v is not None and s.get(k) != v:
                    s[k] = v
                    changed = True
        if changed:
            league.settings = s
            session.commit()
    return league

def _get_or_create_rating(session: Session, league_id: int, agent_id: int, mu0: float, sigma0: float) -> Rating:
    r = session.get(Rating, {"agent_id": agent_id, "league_id": league_id})
    if r is None:
        r = Rating(agent_id=agent_id, league_id=league_id, mu=mu0, sigma=sigma0)
        session.add(r)
    return r

def _apply_trueskill_win(r_winner: Rating, r_loser: Rating, beta: float, tau: float) -> None:
    mu1, s1 = r_winner.mu, r_winner.sigma
    mu2, s2 = r_loser.mu, r_loser.sigma

    # dynamics (prevent sigma→0 and allow time-variance)
    s1 = math.sqrt(s1 * s1 + tau * tau)
    s2 = math.sqrt(s2 * s2 + tau * tau)

    c2 = 2.0 * beta * beta + s1 * s1 + s2 * s2
    c = math.sqrt(c2)
    t = (mu1 - mu2) / c

    # winner side
    v = _v_exceeds(t)
    w = _w_exceeds(t)
    mu1p = mu1 + (s1 * s1 / c) * v
    s1p2 = s1 * s1 * (1.0 - (s1 * s1 / c2) * w)

    # loser side (symmetry at -t)
    vL = _v_exceeds_neg(t)
    wL = _w_exceeds_neg(t)
    mu2p = mu2 - (s2 * s2 / c) * vL
    s2p2 = s2 * s2 * (1.0 - (s2 * s2 / c2) * wL)

    r_winner.mu = float(mu1p)
    r_winner.sigma = float(max(math.sqrt(max(s1p2, EPS)), MIN_SIGMA_ABS))
    r_loser.mu = float(mu2p)
    r_loser.sigma = float(max(math.sqrt(max(s2p2, EPS)), MIN_SIGMA_ABS))

# ---------- incremental update (cursor-based) ----------
def process_new_matches_and_update_ratings(session: Session, league_id: int = 1) -> int:
    league = ensure_league(session, league_id)
    s = dict(league.settings or {})
    mu0 = float(s.get("mu0", TS_DEFAULTS["mu0"]))
    sigma0 = float(s.get("sigma0", TS_DEFAULTS["sigma0"]))
    beta = float(s.get("beta", TS_DEFAULTS["beta"]))
    tau = float(s.get("tau", TS_DEFAULTS["tau"]))
    last_id = int(s.get("last_processed_match_id", 0))

    q = (
        session.query(Match)
        .filter(Match.league_id == league_id)
        .filter(Match.match_id > last_id)
        .order_by(Match.match_id.asc())
    )
    # keep only clean decisive matches
    to_apply = [m for m in q if (m.winner_id is not None and
                                 m.player1_id != m.player2_id and
                                 m.winner_id in {m.player1_id, m.player2_id})]
    if not to_apply:
        return 0

    touched: Dict[int, Rating] = {}
    def get_r(agent_id: int) -> Rating:
        if agent_id not in touched:
            touched[agent_id] = _get_or_create_rating(session, league_id, agent_id, mu0, sigma0)
        return touched[agent_id]

    for m in to_apply:
        r1, r2 = get_r(m.player1_id), get_r(m.player2_id)
        if m.winner_id == m.player1_id:
            _apply_trueskill_win(r1, r2, beta, tau)
        else:
            _apply_trueskill_win(r2, r1, beta, tau)

        now = datetime.datetime.utcnow()
        r1.updated_at = now
        r2.updated_at = now
        last_id = m.match_id

    session.flush()
    s["last_processed_match_id"] = last_id
    league.settings = s
    session.commit()
    return len(to_apply)

# ---------- full rebuild from historical matches ----------
def rebuild_ratings_from_matches(session: Session,
                                 league_id: int = 1,
                                 reset_ratings: bool = True,
                                 order: str = "time",
                                 overrides: Optional[Dict] = None) -> int:
    """
    Recompute ratings from scratch for one league, consuming decisive matches in chronological order.
    order: "time" -> started_at ASC (NULLs first) then match_id; "id" -> match_id ASC.
    Returns number of matches processed.
    """
    league = ensure_league(session, league_id, settings_overrides=overrides, persist_overrides=False)

    # Pull parameters from league (or defaults)
    s = dict(league.settings or {})
    mu0 = float(s.get("mu0", TS_DEFAULTS["mu0"]))
    sigma0 = float(s.get("sigma0", TS_DEFAULTS["sigma0"]))
    beta = float(s.get("beta", TS_DEFAULTS["beta"]))
    tau = float(s.get("tau", TS_DEFAULTS["tau"]))

    # Optionally wipe ratings + cursor
    if reset_ratings:
        session.query(Rating).filter(Rating.league_id == league_id).delete(synchronize_session=False)
        s["last_processed_match_id"] = 0
        league.settings = s
        session.commit()

    # Chronological ordering
    if order == "time":
        q = (
            session.query(Match)
            .filter(Match.league_id == league_id)
            .order_by(Match.started_at.asc().nullsfirst(), Match.match_id.asc())
        )
    else:
        q = (
            session.query(Match)
            .filter(Match.league_id == league_id)
            .order_by(Match.match_id.asc())
        )

    matches = [m for m in q if (m.winner_id is not None and
                                m.player1_id != m.player2_id and
                                m.winner_id in {m.player1_id, m.player2_id})]
    if not matches:
        s["last_processed_match_id"] = 0
        league.settings = s
        session.commit()
        return 0

    # Ratings cache
    cache: Dict[int, Rating] = {}
    def R(agent_id: int) -> Rating:
        r = cache.get(agent_id)
        if r is None:
            r = _get_or_create_rating(session, league_id, agent_id, mu0, sigma0)
            cache[agent_id] = r
        return r

    last_id = 0
    for m in matches:
        r1, r2 = R(m.player1_id), R(m.player2_id)
        if m.winner_id == m.player1_id:
            _apply_trueskill_win(r1, r2, beta, tau)
        else:
            _apply_trueskill_win(r2, r1, beta, tau)

        now = datetime.datetime.utcnow()
        r1.updated_at = now
        r2.updated_at = now
        last_id = m.match_id

    session.flush()
    s["last_processed_match_id"] = last_id
    league.settings = s
    session.commit()
    return len(matches)

# ---------- export leaderboard ----------
def export_ratings_markdown(session: Session, league_id: int, out_path: str, k: float = 3.0) -> None:
    """
    Write a Markdown leaderboard sorted by conservative score: mu - k*sigma.
    """
    rows = (
        session.query(Rating)
        .filter(Rating.league_id == league_id)
        .all()
    )
    if not rows:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("# TrueSkill Leaderboard\n\n(No ratings yet.)\n")
        return

    # Attach agent names
    from league.league_schema import Agent
    aid_to_name = {a.agent_id: a.name for a in session.query(Agent).all()}
    data = []
    for r in rows:
        score = r.mu - k * r.sigma
        data.append((score, r.mu, r.sigma, aid_to_name.get(r.agent_id, f"Agent {r.agent_id}")))

    data.sort(key=lambda t: (-t[0], -t[1], t[3].lower()))

    lines = []
    lines.append("# TrueSkill Leaderboard")
    lines.append("")
    lines.append(f"_Conservative score = μ − {k}·σ_")
    lines.append("")
    lines.append("| Rank | Agent | μ | σ | μ − kσ |")
    lines.append("|---:|---|---:|---:|---:|")
    for idx, (score, mu, sigma, name) in enumerate(data, start=1):
        lines.append(f"| {idx} | {name} | {mu:.2f} | {sigma:.2f} | {score:.2f} |")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

# ---------- CLI ----------
def _parse_args():
    default_league_id = LEAGUE_ID
    p = argparse.ArgumentParser(description="Rebuild or update league ratings from match history.")
    p.add_argument("--league", type=int, default=default_league_id, help="League ID to process (default from run_agents_from_db)")
    p.add_argument("--reset", action="store_true", help="Rebuild ratings from scratch (wipes existing league ratings)")
    p.add_argument("--order", choices=["time", "id"], default="time",
                   help="When rebuilding, order matches by 'time' (started_at asc) or 'id' (default: time)")
    p.add_argument("--update", action="store_true",
                   help="Run incremental update (consume matches after last_processed_match_id)")
    # Optional TS overrides (for this run). Use --persist-settings to save.
    p.add_argument("--mu0", type=float, help="Override prior mu0")
    p.add_argument("--sigma0", type=float, help="Override prior sigma0")
    p.add_argument("--beta", type=float, help="Override performance beta")
    p.add_argument("--tau", type=float, help="Override dynamics tau")
    p.add_argument("--persist-settings", action="store_true",
                   help="Persist any provided TS overrides into league.settings")
    # Export
    p.add_argument("--export-md", type=str, default=None, help="Write a Markdown leaderboard to this path")
    p.add_argument("--k", type=float, default=3.0, help="Conservative k for export (mu - k*sigma)")
    return p.parse_args()

def main():
    args = _parse_args()
    overrides = {k: v for k, v in {
        "mu0": args.mu0,
        "sigma0": args.sigma0,
        "beta": args.beta,
        "tau": args.tau,
    }.items() if v is not None}

    engine = create_engine(get_default_db_path())
    with Session(engine) as session:
        ensure_league(session, league_id=args.league,
                      settings_overrides=overrides if overrides else None,
                      persist_overrides=args.persist_settings)

        if args.update:
            n = process_new_matches_and_update_ratings(session, league_id=args.league)
            print(f"🏅 Incremental update processed {n} new matches.")
        else:
            n = rebuild_ratings_from_matches(session,
                                             league_id=args.league,
                                             reset_ratings=args.reset,
                                             order=args.order,
                                             overrides=overrides if overrides else None)
            mode = "rebuild" if args.reset else "recompute (no wipe)"
            print(f"🏗️  {mode}: processed {n} matches for league {args.league}.")

        if args.export_md:
            out = os.path.abspath(args.export_md)
            export_ratings_markdown(session, args.league, out, k=args.k)
            print(f"📝 Wrote TrueSkill leaderboard: {out}")

if __name__ == "__main__":
    main()
