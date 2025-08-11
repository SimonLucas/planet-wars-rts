# run_agents_from_db.py
import os
import random
import re
import socket
import subprocess
import datetime
from pathlib import Path
from typing import Optional, Tuple, List

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from league.init_db import get_default_db_path
from league_schema import Agent, AgentInstance, Match
from runner_utils.utils import run_command

# ---------- config ----------
DB_PATH = get_default_db_path()
ENGINE = create_engine(DB_PATH)
GAMES_PER_PAIR = 5
REMOTE_TIMEOUT = 50  # ms per remote RPC call


# ---------- helpers ----------
def find_gradlew(start: Optional[Path] = None) -> Path:
    """
    Walk up from this file to find ./gradlew; fall back to ~/GitHub/planet-wars-rts/gradlew.
    """
    start = (start or Path(__file__)).resolve()
    for parent in [start] + list(start.parents):
        gradlew = parent / "gradlew"
        if gradlew.is_file():
            gradlew.chmod(gradlew.stat().st_mode | 0o111)
            return gradlew
    fallback = Path.home() / "GitHub" / "planet-wars-rts" / "gradlew"
    if fallback.exists():
        fallback.chmod(fallback.stat().st_mode | 0o111)
        return fallback
    raise FileNotFoundError("Could not find gradlew")


def sanitize_name(name: str) -> str:
    name = name.lower()
    name = re.sub(r"[^a-z0-9._-]+", "-", name)
    name = re.sub(r"-{2,}", "-", name).strip("-_.")
    if not name:
        raise ValueError("empty name after sanitize")
    return name


def is_container_running(name_or_id: str) -> bool:
    """
    True iff a container exists AND its state is running.
    Safe against empty output / missing container.
    """
    if not name_or_id or len(name_or_id) < 12:  # filter out junk like "99"
        return False
    try:
        out = run_command(["podman", "inspect", "-f", "{{.State.Running}}", name_or_id])
        if not out:
            return False
        return str(out).strip().lower() == "true"
    except subprocess.CalledProcessError:
        return False


def container_exists(name_or_id: str) -> bool:
    if not name_or_id or len(name_or_id) < 12:
        return False
    try:
        out = run_command(["podman", "inspect", name_or_id])
        return bool(out is not None)  # if it didn't raise, it exists
    except subprocess.CalledProcessError:
        return False


def port_is_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except OSError:
            return False


# ---------- gradle output parsing ----------
FOOTER_PATTERNS = {
    "AGENT_A": re.compile(r"^AGENT_A=(.*)$", re.MULTILINE),
    "AGENT_B": re.compile(r"^AGENT_B=(.*)$", re.MULTILINE),
    "PORT_A": re.compile(r"^PORT_A=(\d+)$", re.MULTILINE),
    "PORT_B": re.compile(r"^PORT_B=(\d+)$", re.MULTILINE),
    "WINS_A": re.compile(r"^WINS_A=(\d+)$", re.MULTILINE),
    "WINS_B": re.compile(r"^WINS_B=(\d+)$", re.MULTILINE),
    "DRAWS": re.compile(r"^DRAWS=(\d+)$", re.MULTILINE),
    "TOTAL_GAMES": re.compile(r"^TOTAL_GAMES=(\d+)$", re.MULTILINE),
}


def parse_footer(text: str) -> dict:
    out = {}
    for key, pat in FOOTER_PATTERNS.items():
        m = pat.search(text)
        if not m:
            raise ValueError(f"Missing {key} in Gradle output")
        out[key] = m.group(1)
    # cast numerics
    for k in ("PORT_A", "PORT_B", "WINS_A", "WINS_B", "DRAWS", "TOTAL_GAMES"):
        out[k] = int(out[k])
    return out


# ---------- run one evaluation ----------
def run_remote_pair_evaluation(port_a: int, port_b: int, games_per_pair: int, timeout_ms: int) -> dict:
    gradlew = find_gradlew(Path(__file__).resolve())
    cwd = gradlew.parent
    args_csv = f"{port_a},{port_b},{games_per_pair},{timeout_ms}"
    cmd = [str(gradlew), "runRemotePairEvaluation", f"--args={args_csv}"]
    print(f"⚙️  {cmd}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            "Gradle task failed:\n"
            f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
        )
    return parse_footer(result.stdout)


# ---------- selection ----------
def list_active_agents(session: Session) -> List[Tuple[Agent, AgentInstance, bool]]:
    """
    Returns [(Agent, AgentInstance, is_active)] where is_active is True if the container
    is running OR the port is listening. Skips dummy port 123 and junk container IDs.
    """
    rows = (
        session.query(Agent, AgentInstance)
        .join(AgentInstance, Agent.agent_id == AgentInstance.agent_id)
        .all()
    )

    out: List[Tuple[Agent, AgentInstance, bool]] = []
    for agent, inst in rows:
        # Skip dummy or obviously invalid rows
        if inst.port == 123:
            out.append((agent, inst, False))
            continue

        running = False

        # Prefer container_id if present and looks legit
        cid = (inst.container_id or "").strip()
        if len(cid) >= 12 and is_container_running(cid):
            running = True

        # Fallback: deterministic container name
        if not running:
            cname = f"container-{sanitize_name(agent.name)}"
            # For names, we don't enforce 12-char check
            if is_container_running(cname):
                running = True

        # Last fallback: the port is open
        if not running and port_is_listening(inst.port):
            running = True

        out.append((agent, inst, running))
    return out


def pick_two_random_active(session: Session) -> Tuple[Tuple[Agent, AgentInstance], Tuple[Agent, AgentInstance]]:
    triples = list_active_agents(session)
    active = [(a, inst) for (a, inst, ok) in triples if ok]
    print(f"🔍 Found {len(active)} active agents")
    if len(active) < 2:
        raise RuntimeError("Not enough active agents to run a match")
    return tuple(random.sample(active, 2))  # type: ignore[return-value]


# ---------- DB write ----------
def store_matches(session: Session, league_id: int, a: Agent, b: Agent, wins_a: int, wins_b: int, draws: int) -> int:
    """
    Insert one Match row per decided game (winner_id required by schema).
    Draws are currently skipped because winner_id is non-nullable.
    """
    inserted = 0
    meta = {"mode": "remote_pair"}
    now = datetime.datetime.now()

    for _ in range(wins_a):
        session.add(Match(
            league_id=league_id,
            player1_id=a.agent_id,
            player2_id=b.agent_id,
            map_name="auto",
            seed=0,
            game_params=meta,
            started_at=now,
            finished_at=now,
            winner_id=a.agent_id,
            player1_score=1,
            player2_score=0,
            log_url="",
        ))
        inserted += 1

    for _ in range(wins_b):
        session.add(Match(
            league_id=league_id,
            player1_id=a.agent_id,
            player2_id=b.agent_id,
            map_name="auto",
            seed=0,
            game_params=meta,
            started_at=now,
            finished_at=now,
            winner_id=b.agent_id,
            player1_score=0,
            player2_score=1,
            log_url="",
        ))
        inserted += 1

    # If/when winner_id becomes nullable, we can also store draws here.
    if draws:
        pass

    return inserted


# ---------- main ----------
def main(n_pairs: int = 1):
    with Session(ENGINE) as session:
        total_with_instances = (
            session.query(Agent)
            .join(AgentInstance, Agent.agent_id == AgentInstance.agent_id)
            .count()
        )
        print(f"🔍 Found {total_with_instances} agents with instances")
        if total_with_instances < 2:
            print("❌ Not enough agents with instances to run matches. Exiting.")
            return

        for i in range(n_pairs):
            print(f"\n🔄 Running pair {i + 1}/{n_pairs}...")

            (a, inst_a), (b, inst_b) = pick_two_random_active(session)
            print(f"🎯 Selected: {a.name} (port {inst_a.port}) vs {b.name} (port {inst_b.port})")

            try:
                footer = run_remote_pair_evaluation(inst_a.port, inst_b.port, GAMES_PER_PAIR, REMOTE_TIMEOUT)
            except RuntimeError as e:
                print(f"❌ Pair {i + 1} failed: {e}")
                # Optional: mark suspected culprit and continue
                continue

            # sanity vs gradle output (won't stop execution)
            if footer["PORT_A"] != inst_a.port or footer["PORT_B"] != inst_b.port:
                print("⚠️  Port mismatch between DB and Gradle output; continuing.")

            wins_a, wins_b = footer["WINS_A"], footer["WINS_B"]
            draws, total = footer["DRAWS"], footer["TOTAL_GAMES"]

            # Update last_seen for both instances
            now = datetime.datetime.now()
            inst_a.last_seen = now
            inst_b.last_seen = now
            session.commit()

            inserted = store_matches(session, league_id=1, a=a, b=b, wins_a=wins_a, wins_b=wins_b, draws=draws)
            session.commit()

            print(
                f"📦 Stored matches: {a.name} (wins={wins_a}) vs {b.name} (wins={wins_b}), "
                f"draws={draws}, total={total}. Inserted {inserted} rows."
            )


if __name__ == "__main__":
    main(20)
