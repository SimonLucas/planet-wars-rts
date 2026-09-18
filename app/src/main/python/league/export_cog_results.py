"""Export the corrected CoG round robin, using one representative per entrant."""
from __future__ import annotations

import argparse
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from league.cog_2026_config import COG_LEAGUE_ID, selected_names
from league.init_db import get_default_db_path
from league.round_robin_top_n import fetch_agents_by_name, compute_head_to_head, build_markdown


def overall(agent_id: int, ids: list[int], h2h: dict) -> float:
    rates = [wins / games for opponent in ids if opponent != agent_id
             for wins, games in [h2h.get((agent_id, opponent), (0, 0))] if games]
    return sum(rates) / len(rates) if rates else -1.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--league', type=int, default=COG_LEAGUE_ID)
    ap.add_argument('--variant', choices=['metang', 'metagross'], default='metang',
                    help='Select the mnn31 representative for this 10-agent export.')
    ap.add_argument('--db', help='SQLAlchemy database URL')
    ap.add_argument('--out-dir', type=Path, default=Path.home() / 'spring-2026')
    args = ap.parse_args()
    names = selected_names(args.variant)
    db_url = args.db or get_default_db_path()
    with Session(create_engine(db_url)) as session:
        agents = fetch_agents_by_name(session, args.league, names)
        ids = [a['agent_id'] for a in agents]
        h2h = compute_head_to_head(session, args.league, ids)
    # Re-rank after filtering, using only the remaining opponents.
    agents.sort(key=lambda a: (-overall(a['agent_id'], ids, h2h), a['name']))
    stem = f'round_robin_cog_2026_league{args.league}_{args.variant}'
    args.out_dir.mkdir(parents=True, exist_ok=True)
    md_path = args.out_dir / f'{stem}.md'
    md = build_markdown(agents, h2h, f'CoG 2026 corrected run / league {args.league}')
    md += ('\nRows ordered by mean win rate against the selected opponents. '
           'Unplayed opponents are omitted from the mean; incomplete tables are provisional.\n')
    md_path.write_text(md)
    print(f'Wrote {md_path}')
    from league.export_cog_heatmap import generate
    generate(args.out_dir / f'{stem}.png', league_id=args.league,
             names=[a['name'] for a in agents], db_url=db_url)


if __name__ == '__main__':
    main()
