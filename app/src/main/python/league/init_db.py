# init_db.py

from sqlalchemy import create_engine

from league.config import EVAL_PHASE
from league.league_schema import Base
from pathlib import Path

def get_default_db_path() -> str:
    """Returns a platform-independent default DB path."""
    db_dir = Path.home() / EVAL_PHASE
    db_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_dir / 'new-league.db'}"

def init_db(db_path: str = None):
    db_url = db_path if db_path else get_default_db_path()
    print(f"🛠️  Initializing league database at {db_url}")

    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    print("✅ League database initialized successfully.")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=str, help="Optional full database URI (e.g. sqlite:////tmp/custom.db)")
    args = parser.parse_args()

    init_db(args.db)

