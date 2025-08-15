#!/usr/bin/env python3
from __future__ import annotations
import sqlite3
from pathlib import Path
from sqlalchemy.engine import make_url   # ← helps parse the URL
from league.init_db import get_default_db_path

def resolve_sqlite_path(url_or_path: str) -> str:
    if url_or_path.startswith("sqlite:"):
        u = make_url(url_or_path)
        return u.database or ":memory:"
    return url_or_path

def main() -> None:
    url = get_default_db_path()
    db_path = resolve_sqlite_path(url)
    p = Path(db_path)
    if not p.exists():
        raise SystemExit(f"DB file not found at {p}")

    with sqlite3.connect(db_path) as con:
        con.execute("PRAGMA foreign_keys=ON;")
        # If WAL is on, checkpoint it and truncate
        con.execute("PRAGMA wal_checkpoint(TRUNCATE);")

        jm   = con.execute("PRAGMA journal_mode;").fetchone()[0]
        quick= con.execute("PRAGMA quick_check;").fetchone()[0]
        integ= con.execute("PRAGMA integrity_check;").fetchone()[0]
        fk   = con.execute("PRAGMA foreign_key_check;").fetchall()

    print(f"DB: {db_path}")
    print(f"journal_mode: {jm}")
    print(f"quick_check: {quick}")
    print(f"integrity_check: {integ}")
    print(f"foreign_key_issues: {len(fk)}")

if __name__ == "__main__":
    main()
