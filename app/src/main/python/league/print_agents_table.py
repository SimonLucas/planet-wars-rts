from sqlalchemy.orm import Session
from pathlib import Path

from league.init_db import get_default_db_path
from league_schema import Agent, Base, AgentInstance
from sqlalchemy import create_engine

# 🔧 Path to your SQLite DB (adjust if needed)
DB_PATH = get_default_db_path()
engine = create_engine(DB_PATH)


def print_all_agents():
    with Session(engine) as session:
        agents = session.query(Agent).order_by(Agent.created_at).all()
        if not agents:
            print("No agents found.")
            return

        print(f"{'ID':<4} {'Name':<25} {'Owner':<15} {'Commit':<10} {'Repo':<40} {'Created'}")
        print("=" * 110)
        for agent in agents:
            print(f"{agent.agent_id:<4} {agent.name:<25} {agent.owner:<15} "
                  f"{agent.commit[:7] if agent.commit else '—':<10} "
                  f"{agent.repo_url:<40} {agent.created_at.strftime('%Y-%m-%d %H:%M:%S')}")


def print_all_agent_instances():
    with Session(engine) as session:
        instances = session.query(AgentInstance).order_by(AgentInstance.last_seen.desc()).all()

        if not instances:
            print("No agent instances found.")
            return

        print(f"{'AgentID':<8} {'Name':<25} {'Port':<6} {'Container ID':<20} {'Last Seen'}")
        print("=" * 80)

        for instance in instances:
            agent = instance.agent  # via relationship
            print(f"{instance.agent_id:<8} "
                  f"{agent.name if agent else '—':<25} "
                  f"{instance.port:<6} "
                  f"{instance.container_id:<20} "
                  f"{instance.last_seen.strftime('%Y-%m-%d %H:%M:%S')}")



from sqlalchemy.orm import Session, joinedload
from league_schema import Agent, Base, AgentInstance, Match, League  # add Match, League
# (rest of your imports stay the same)

def print_all_matches(league_id=None, agent_id=None, limit=200):
    with Session(engine) as session:
        q = (
            session.query(Match)
            .options(
                joinedload(Match.league),
                joinedload(Match.player1),
                joinedload(Match.player2),
                joinedload(Match.winner),
            )
            .order_by(Match.match_id.desc())
        )
        if league_id is not None:
            q = q.filter(Match.league_id == league_id)
        if agent_id is not None:
            q = q.filter((Match.player1_id == agent_id) | (Match.player2_id == agent_id))
        if limit:
            q = q.limit(limit)

        matches = q.all()
        if not matches:
            print("No matches found.")
            return

        header = (
            f"{'ID':<6} {'League':<18} {'P1':<22} {'P2':<22} "
            f"{'Winner':<22} {'Score':<9} {'Seed':<6} {'Map':<16} "
            f"{'Started':<19} {'Finished':<19}"
        )
        print(header)
        print("=" * len(header))

        for m in matches:
            league_name = m.league.name if m.league else str(m.league_id)
            p1 = m.player1.name if m.player1 else f"#{m.player1_id}"
            p2 = m.player2.name if m.player2 else f"#{m.player2_id}"
            if m.winner:
                winner = m.winner.name
            elif m.winner_id == m.player1_id:
                winner = p1
            elif m.winner_id == m.player2_id:
                winner = p2
            else:
                winner = "—"

            score = (
                f"{m.player1_score}-{m.player2_score}"
                if (m.player1_score is not None and m.player2_score is not None)
                else "—"
            )
            started = m.started_at.strftime("%Y-%m-%d %H:%M:%S") if m.started_at else "—"
            finished = m.finished_at.strftime("%Y-%m-%d %H:%M:%S") if m.finished_at else "—"

            print(
                f"{m.match_id:<6} {league_name:<18} {p1:<22} {p2:<22} "
                f"{winner:<22} {score:<9} {m.seed:<6} {m.map_name:<16} "
                f"{started:<19} {finished:<19}"
            )

if __name__ == "__main__":
    print_all_agents()
    print()
    print_all_agent_instances()
    print()
    print_all_matches(league_id=2, limit=10)  # Adjust limit as needed
