# export_leaderboard_md.py
import argparse
from collections import defaultdict
from datetime import timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Your models & DB helper
from league.init_db import get_default_db_path
from league.league_schema import Agent, League, Match, Rating
from league.run_agents_from_db import LEAGUE_ID


def get_md_table_path() -> Path:
    """Returns a platform-independent default DB path."""
    md_table_dir = Path.home() / "GitHub/planet-wars-rts-submissions/results/autumn-2025"
    md_table_dir.mkdir(parents=True, exist_ok=True)
    return md_table_dir / "leaderboard.md"


def load_matches_played(session: Session, league_id: int) -> dict[int, int]:
    """
    Count how many decisive matches (winner_id NOT NULL) each agent has played in this league.
    """
    counts: dict[int, int] = defaultdict(int)
    q = (
        session.query(Match.player1_id, Match.player2_id)
        .filter(Match.league_id == league_id)
        .filter(Match.winner_id.isnot(None))
    )
    for p1, p2 in q:
        counts[p1] += 1
        counts[p2] += 1
    return counts


def fetch_leaderboard_rows(session: Session, league_id: int) -> list[dict]:
    """
    Join Rating→Agent, compute conservative rating (mu - 3*sigma), attach matches played.
    """
    matches_played = load_matches_played(session, league_id)

    rows = []
    q = (
        session.query(Rating, Agent)
        .join(Agent, Rating.agent_id == Agent.agent_id)
        .filter(Rating.league_id == league_id)
    )
    for r, a in q:
        conservative = r.mu - 3.0 * r.sigma
        rows.append(
            {
                "agent_id": a.agent_id,
                "agent": a.name,
                "owner": a.owner or "unknown",
                "mu": float(r.mu),
                "sigma": float(r.sigma),
                "conservative": float(conservative),
                "matches": int(matches_played.get(a.agent_id, 0)),
                "updated_at": r.updated_at,
            }
        )
    # Sort by conservative rating desc, then by mu desc as a stable tiebreaker
    rows.sort(key=lambda d: (d["conservative"], d["mu"]), reverse=True)
    return rows


def to_markdown(rows: list[dict], league_name: str, limit: int | None) -> str:
    # ignore owner for now, as it is currently always unknown
    # old_header = [
    #     f"# {league_name} — Leaderboard",
    #     "",
    #     "| # | Agent | Owner | μ | σ | μ − 3σ | Matches | Updated |",
    #     "|---:|---|---|---:|---:|---:|---:|---|",
    # ]
    header = [
        f"# {league_name} — Leaderboard",
        "",
        "| # | Agent | μ | σ | μ − 3σ | Matches | Updated |",
        "|---:|---|---:|---:|---:|---:|---|",
    ]
    body = []
    chosen = rows if limit is None else rows[:limit]
    for i, r in enumerate(chosen, 1):
        updated = r["updated_at"]
        # Show UTC time compactly
        if updated and updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        updated_str = updated.strftime("%Y-%m-%d %H:%M") if updated else ""
        body.append(
            f"| {i} | {r['agent']} | " # {r['owner']} | "
            f"{r['mu']:.3f} | {r['sigma']:.3f} | {r['conservative']:.3f} | "
            f"{r['matches']} | {updated_str} |"
        )
    return "\n".join(header + body) + "\n"


def main():
    ap = argparse.ArgumentParser(
        description="Export a Markdown leaderboard from ratings + match counts."
    )
    default_league_id = LEAGUE_ID
    ap.add_argument("--league", type=int, default=default_league_id, help="League ID (default: 1)")
    ap.add_argument("--limit", type=int, default=200, help="Max rows in table (default: 200)")
    ap.add_argument(
        "--out",
        type=str,
        default=get_md_table_path(),
        help="Output Markdown file (default: leaderboard.md)",
    )
    args = ap.parse_args()

    engine = create_engine(get_default_db_path())
    with Session(engine) as session:
        league = session.get(League, args.league)
        league_name = league.name if league else f"League {args.league}"

        # hard override the league name - a quick hack
        league_name = "IEEE CoG 2025"

        rows = fetch_leaderboard_rows(session, args.league)
        md = to_markdown(rows, league_name, limit=args.limit)

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"✅ Wrote {len(rows[:args.limit])} rows to {args.out}")


if __name__ == "__main__":
    main()
