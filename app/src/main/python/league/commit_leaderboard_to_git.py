#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from league.export_leaderboard_md import get_md_table_path

REMOTE: str = "origin"  # local alias for your GitHub remote


# def get_md_table_path() -> Path:
#     """Return the canonical path to the leaderboard within the submissions repo."""
#     md_table_dir = Path.home() / "GitHub" / "planet-wars-rts-submissions" / "results" / "ieee-cog-2025"
#     md_table_dir.mkdir(parents=True, exist_ok=True)
#     return md_table_dir / "leaderboard.md"


def find_repo_root(start: Path) -> Path:
    """
    Walk up from 'start' until a '.git' directory is found and return that directory.
    Exits with code 1 if no repo root is found.
    """
    cur = start.resolve()
    for p in (cur,) + tuple(cur.parents):
        if (p / ".git").exists():
            return p
    print(f"❌ Could not find a git repository above: {start}", file=sys.stderr)
    sys.exit(1)


def git_out(repo: Path, *args: str) -> str:
    """Run a git command and return stdout (stripped)."""
    return subprocess.check_output(args, cwd=repo, text=True).strip()


def git_run(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a git command, capturing output."""
    return subprocess.run(args, cwd=repo, text=True, capture_output=True, check=check)


def main() -> None:
    md_path: Path = get_md_table_path()
    if not md_path.exists():
        print(
            "❌ Leaderboard file not found:\n"
            f"   {md_path}\n"
            "   Generate it first, then re-run this script.",
            file=sys.stderr,
        )
        sys.exit(1)

    repo_root: Path = find_repo_root(md_path)
    rel_path: Path = md_path.relative_to(repo_root)  # path to stage inside the repo

    # Determine current branch
    try:
        branch: str = git_out(repo_root, "git", "rev-parse", "--abbrev-ref", "HEAD")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to get current branch:\n{e}", file=sys.stderr)
        sys.exit(1)

    # Stage the leaderboard (by relative path)
    try:
        git_run(repo_root, "git", "add", rel_path.as_posix(), check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ git add failed:\n{e.stdout}\n{e.stderr}", file=sys.stderr)
        sys.exit(e.returncode)

    # Commit (graceful no-op if nothing changed)
    msg: str = f"Update leaderboard: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC"
    commit = git_run(repo_root, "git", "commit", "-m", msg, check=False)
    if commit.returncode != 0:
        combined = (commit.stdout + "\n" + commit.stderr).lower()
        if "nothing to commit" in combined or "no changes added to commit" in combined or "working tree clean" in combined:
            print("ℹ️  No changes to commit. Nothing to push.")
            return
        print(f"❌ git commit failed:\n{commit.stdout}\n{commit.stderr}", file=sys.stderr)
        sys.exit(commit.returncode)

    # Push to the same branch
    try:
        git_run(repo_root, "git", "push", REMOTE, f"HEAD:{branch}", check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ git push failed:\n{e.stdout}\n{e.stderr}", file=sys.stderr)
        sys.exit(e.returncode)

    print(f"✅ Pushed {rel_path.as_posix()} to {REMOTE}/{branch}")


if __name__ == "__main__":
    main()
