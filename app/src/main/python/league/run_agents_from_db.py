# run_agents_from_db.py
import os
import random
import re
import socket
import subprocess
import datetime
import time
from pathlib import Path
from typing import Optional, Tuple, List, Dict

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from league.init_db import get_default_db_path
from league.league_schema import Agent, AgentInstance, Match
from league.scheduler import choose_next_pair

# ---------- config ----------
DB_PATH = get_default_db_path()
ENGINE = create_engine(DB_PATH)
GAMES_PER_PAIR = 10
REMOTE_TIMEOUT = 50  # ms per remote RPC call

# Podman robustness controls
PODMAN_TIMEOUT_SHORT = 4
PODMAN_TIMEOUT_LONG = 8
PS_CACHE_TTL_SECS = 20
PS_BACKOFF_SECS = 60

# Start/wait behavior
START_WAIT_SECS = 12
HEAL_WAIT_SECS = 3
RESTART_COOLDOWN_SECS = 30
MAX_RETRY_ON_WS_CLOSE = 1

# Discovery assist
PROBE_CANDIDATES = 6
LEAGUE_ID = 5  # default league ID for remote pair runs

# Quarantine/backoff when WS blows up
WS_ERROR_BACKOFF_SECS = 60  # keep problematic agents out of the pool briefly


# ---------- helpers ----------
def find_gradlew(start: Optional[Path] = None) -> Path:
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


# def _run_podman(args: List[str], timeout: int) -> Tuple[int, str, str]:
#     try:
#         p = subprocess.run(["podman", *args], capture_output=True, text=True, timeout=timeout)
#         return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()
#     except subprocess.TimeoutExpired:
#         return 124, "", f"timeout after {timeout}s: podman {' '.join(args)}"
#     except Exception as e:
#         return 125, "", f"{type(e).__name__}: {e}"

from typing import List, Tuple
import subprocess

def _run_podman(args: List[str], timeout: int) -> Tuple[int, str, str]:
    """
    Drop-in replacement that injects '--log-driver=none' for 'podman run'/'create'
    to prevent container stdout/stderr from being forwarded to journald/syslog.

    Returns: (returncode, stdout_stripped, stderr_stripped)
    """
    try:
        adj = list(args)

        # Find the subcommand index ('run' or 'create')
        sub_idx = None
        for i, tok in enumerate(adj):
            if tok in ("run", "create"):
                sub_idx = i
                break

        # Only inject for run/create, and only if not already specified
        if sub_idx is not None and "--log-driver" not in adj:
            insert_pos = sub_idx + 1  # directly after 'run'/'create'
            adj[insert_pos:insert_pos] = ["--log-driver", "none"]
            # If you prefer rotated file logs instead, replace the line above with:
            # adj[insert_pos:insert_pos] = [
            #     "--log-driver", "k8s-file",
            #     "--log-opt", "max-size=10mb",
            #     "--log-opt", "max-file=5",
            # ]

        p = subprocess.run(
            ["podman", *adj],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()

    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s: podman {' '.join(args)}"
    except Exception as e:
        return 125, "", f"{type(e).__name__}: {e}"



def is_container_running(name_or_id: str) -> bool:
    if not name_or_id:
        return False
    rc, out, _ = _run_podman(["inspect", "-f", "{{.State.Running}}", name_or_id], PODMAN_TIMEOUT_SHORT)
    return rc == 0 and out.lower() == "true"


def container_exists(name_or_id: str) -> bool:
    if not name_or_id:
        return False
    rc, _, _ = _run_podman(["inspect", name_or_id], PODMAN_TIMEOUT_SHORT)
    return rc == 0


def port_is_listening(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.25)
        try:
            s.connect((host, port))
            return True
        except OSError:
            return False


def wait_for_port(port: int, host: str = "127.0.0.1", timeout: float = START_WAIT_SECS) -> bool:
    t0 = time.time()
    print(f"⏳ Waiting for port {port} (up to {timeout}s)...")
    while time.time() - t0 < timeout:
        if port_is_listening(port, host):
            print(f"✅ Port {port} is up.")
            return True
        time.sleep(0.25)
    print(f"⌛ Gave up waiting for port {port}.")
    return False


def start_container(name_or_id: str) -> None:
    print(f"🟡 Starting {name_or_id}…")
    _run_podman(["start", name_or_id], PODMAN_TIMEOUT_LONG)


def restart_container(name_or_id: str) -> None:
    print(f"🟠 Restarting {name_or_id}…")
    _run_podman(["restart", name_or_id], PODMAN_TIMEOUT_LONG)


def host_port_from_podman(name_or_id: str) -> Optional[int]:
    rc, out, _ = _run_podman(["port", name_or_id], PODMAN_TIMEOUT_SHORT)
    if rc != 0 or not out:
        return None
    m = re.search(r"-> .*:(\d+)", out)
    return int(m.group(1)) if m else None


# ----- ps -a caching & backoff -----
_ps_cache_names: List[str] = []
_ps_cache_ts: float = 0.0
_ps_backoff_until: float = 0.0


def _get_ps_names_cached() -> List[str]:
    global _ps_cache_names, _ps_cache_ts, _ps_backoff_until
    now = time.time()
    if now < _ps_backoff_until and _ps_cache_names:
        return _ps_cache_names
    if now - _ps_cache_ts <= PS_CACHE_TTL_SECS and _ps_cache_names:
        return _ps_cache_names

    rc, out, err = _run_podman(["ps", "-a", "--format", "{{.Names}}"], PODMAN_TIMEOUT_LONG)
    if rc == 0 and out:
        _ps_cache_names = [ln.strip() for ln in out.splitlines() if ln.strip()]
        _ps_cache_ts = now
        return _ps_cache_names

    _ps_backoff_until = now + PS_BACKOFF_SECS
    return _ps_cache_names


def find_container_by_prefix(prefix: str) -> Optional[str]:
    names = _get_ps_names_cached()
    for name in names:
        if name.startswith(prefix):
            return name
    return None


# restart cooldown
_restart_cooldown: Dict[str, float] = {}


def _cooldown_ok(identifier: str) -> bool:
    now = time.time()
    nxt = _restart_cooldown.get(identifier, 0.0)
    return now >= nxt


def _bump_cooldown(identifier: str, seconds: float = RESTART_COOLDOWN_SECS) -> None:
    _restart_cooldown[identifier] = time.time() + seconds


def resolve_container_identifier(agent: Agent, inst: AgentInstance) -> Optional[str]:
    cid = (inst.container_id or "").strip()
    if cid and container_exists(cid):
        return cid
    prefix = f"container-{sanitize_name(agent.name)}"
    return find_container_by_prefix(prefix)


def ensure_ready(agent: Agent, inst: AgentInstance, *, quick: bool = False) -> Tuple[bool, Optional[str], int]:
    wait_budget = HEAL_WAIT_SECS if quick else START_WAIT_SECS

    identifier = resolve_container_identifier(agent, inst)

    if port_is_listening(inst.port):
        return True, identifier, inst.port

    if not identifier:
        ok = wait_for_port(inst.port, timeout=wait_budget)
        return ok, None, inst.port

    if not is_container_running(identifier) and _cooldown_ok(identifier):
        start_container(identifier)
        _bump_cooldown(identifier)

    port = inst.port
    if not port_is_listening(port):
        p = host_port_from_podman(identifier)
        if p:
            port = p

    ok = wait_for_port(port, timeout=wait_budget)
    return ok, identifier, port


# ---------- retryable error classification ----------
RETRYABLE_ERROR_PATS = [
    re.compile(r"ClosedReceiveChannelException", re.I),
    re.compile(r"Channel was cancelled", re.I),  # <-- your failure
    re.compile(r"ClosedChannelException", re.I),
    re.compile(r"WebSocket.*(closed|failure)", re.I),
    re.compile(r"Connection reset", re.I),
    re.compile(r"broken pipe", re.I),
]


def is_retryable_ws_error(text: str) -> bool:
    return any(p.search(text or "") for p in RETRYABLE_ERROR_PATS)


# quarantine registry (by Agent.agent_id)
_agent_backoff_until: Dict[int, float] = {}


def _is_quarantined(agent_id: int) -> bool:
    return time.time() < _agent_backoff_until.get(agent_id, 0.0)


def _quarantine(agent_id: int, seconds: int = WS_ERROR_BACKOFF_SECS) -> None:
    _agent_backoff_until[agent_id] = time.time() + seconds


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
    for k in ("PORT_A", "PORT_B", "WINS_A", "WINS_B", "DRAWS", "TOTAL_GAMES"):
        out[k] = int(out[k])
    return out


# ---------- run one evaluation ----------
def run_remote_pair_evaluation(port_a: int, port_b: int, games_per_pair: int, timeout_ms: int) -> Tuple[bool, Optional[dict], str]:
    gradlew = find_gradlew(Path(__file__).resolve())
    cwd = gradlew.parent
    args_csv = f"{port_a},{port_b},{games_per_pair},{timeout_ms}"
    cmd = [str(gradlew), "runRemotePairEvaluation", f"--args={args_csv}"]
    print(f"⚙️  {cmd}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    combined = f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
    if result.returncode != 0:
        return False, None, combined
    try:
        footer = parse_footer(result.stdout)
    except Exception as e:
        return False, None, combined + f"\n\nPARSE_ERROR: {e}"
    return True, footer, combined


def run_pair_with_auto_rescue(a: Agent, inst_a: AgentInstance, b: Agent, inst_b: AgentInstance) -> Optional[dict]:
    ok_a, ident_a, port_a = ensure_ready(a, inst_a, quick=False)
    ok_b, ident_b, port_b = ensure_ready(b, inst_b, quick=False)
    if not (ok_a and ok_b):
        print(f"⛔ Not ready: {a.name if not ok_a else ''} {b.name if not ok_b else ''}".strip())
        return None

    ok, footer, text = run_remote_pair_evaluation(port_a, port_b, GAMES_PER_PAIR, REMOTE_TIMEOUT)
    if ok:
        return footer

    if not is_retryable_ws_error(text):
        print(f"❌ Pair failed (no retry):\n{text}")
        return None

    print("🔁 WebSocket closed/cancelled mid-run; restarting both and retrying once…")
    if ident_a:
        restart_container(ident_a)
    if ident_b:
        restart_container(ident_b)

    if not wait_for_port(port_a, timeout=START_WAIT_SECS) or not wait_for_port(port_b, timeout=START_WAIT_SECS):
        print("⛔ Ports not ready after restart; giving up on this pair.")
        # quarantine both briefly to avoid immediate reselection
        _quarantine(a.agent_id); _quarantine(b.agent_id)
        return None

    ok2, footer2, text2 = run_remote_pair_evaluation(port_a, port_b, GAMES_PER_PAIR, REMOTE_TIMEOUT)
    if ok2:
        return footer2

    # Still failed: quarantine both agents briefly
    if is_retryable_ws_error(text2):
        print("🧯 Retry hit another transient WS error; quarantining both agents for a bit.")
        _quarantine(a.agent_id); _quarantine(b.agent_id)
    print(f"❌ Retry failed:\n{text2}")
    return None


# ---------- selection ----------
def _rows_with_instances(session: Session) -> List[Tuple[Agent, AgentInstance]]:
    return (
        session.query(Agent, AgentInstance)
        .join(AgentInstance, Agent.agent_id == AgentInstance.agent_id)
        .all()
    )


def list_active_agents(session: Session) -> List[Tuple[Agent, AgentInstance, bool]]:
    """
    Returns [(Agent, AgentInstance, is_active)].
    Active == port open OR container appears to be running.
    Does not start containers.
    Respects quarantine.
    """
    rows = _rows_with_instances(session)
    out: List[Tuple[Agent, AgentInstance, bool]] = []

    for agent, inst in rows:
        if _is_quarantined(agent.agent_id):
            out.append((agent, inst, False))
            continue

        if inst.port == 123:
            out.append((agent, inst, False))
            continue

        if port_is_listening(inst.port):
            out.append((agent, inst, True))
            continue

        running = False
        cid = (inst.container_id or "").strip()
        if cid and is_container_running(cid):
            running = True
        elif not cid:
            cname = find_container_by_prefix(f"container-{sanitize_name(agent.name)}")
            if cname and is_container_running(cname):
                running = True

        out.append((agent, inst, running))
    return out


# def pick_two_ready_or_probe(session: Session) -> Tuple[Tuple[Agent, AgentInstance], Tuple[Agent, AgentInstance]]:
#     triples = list_active_agents(session)
#     active = [(a, inst) for (a, inst, ok) in triples if ok]
#     print(f"🔍 Found {len(active)} active agents")
#
#     if len(active) >= 2:
#         return tuple(random.sample(active, 2))  # type: ignore[return-value]
#
#     # Not enough: probe a few random candidates to wake them up.
#     rows = _rows_with_instances(session)
#     random.shuffle(rows)
#     print("🧪 Probing a few candidates to wake them (short heal)…")
#     woken: List[Tuple[Agent, AgentInstance]] = []
#     tried = 0
#     for agent, inst in rows:
#         if _is_quarantined(agent.agent_id):
#             continue
#         if tried >= PROBE_CANDIDATES or len(active) + len(woken) >= 4:
#             break
#         tried += 1
#         ok, _, _ = ensure_ready(agent, inst, quick=True)
#         if ok:
#             woken.append((agent, inst))
#
#     active.extend(woken)
#     print(f"🔎 Active after probe: {len(active)}")
#     if len(active) < 2:
#         raise RuntimeError("Not enough active agents to run a match")
#     return tuple(random.sample(active, 2))  # type: ignore[return-value]
#

def random_choose_next_pair(ids: List[int]) -> Tuple[int, int]:
    """
    Randomly choose a pair of agent IDs from the provided list.
    """
    if len(ids) < 2:
        raise ValueError("Not enough agent IDs to choose a pair")
    return tuple(random.sample(ids, 2))

def pick_two_ready_or_probe(session: Session) -> Tuple[Tuple[Agent, AgentInstance], Tuple[Agent, AgentInstance]]:
    """
    Use adaptive scheduler to choose a pair; ensure they're (quick) ready; if not,
    fall back to existing 'probe & random' strategy.
    """
    # Map agent_id -> (Agent, AgentInstance) for quick lookup
    rows = _rows_with_instances(session)
    id2row: Dict[int, Tuple[Agent, AgentInstance]] = {a.agent_id: (a, inst) for a, inst in rows}

    # 1) Try policy-guided pair
    # chosen = choose_next_pair(session, league_id=LEAGUE_ID)  # returns (aid_a, aid_b) or None
    chosen = random_choose_next_pair(list(id2row.keys()))
    if chosen:
        aid_a, aid_b = chosen
        pair_rows: List[Tuple[Agent, AgentInstance]] = []
        for aid in (aid_a, aid_b):
            row = id2row.get(aid)
            if row is None:
                # No running instance for this agent – bail to fallback
                pair_rows = []
                break
            a, inst = row
            if _is_quarantined(a.agent_id):
                pair_rows = []
                break
            # Try to wake quickly
            ok, _, _ = ensure_ready(a, inst, quick=True)
            if not ok:
                pair_rows = []
                break
            pair_rows.append((a, inst))

        if len(pair_rows) == 2:
            return pair_rows[0], pair_rows[1]

    # 2) Fallback = your existing path (probe + random among active)
    triples = list_active_agents(session)
    active = [(a, inst) for (a, inst, ok) in triples if ok]
    if len(active) >= 2:
        return tuple(random.sample(active, 2))  # type: ignore[return-value]

    # Probe a few to try to wake them (short heal), then random among active+woken
    rows = _rows_with_instances(session)
    random.shuffle(rows)
    woken: List[Tuple[Agent, AgentInstance]] = []
    tried = 0
    for agent, inst in rows:
        if _is_quarantined(agent.agent_id):
            continue
        if tried >= PROBE_CANDIDATES or len(active) + len(woken) >= 4:
            break
        tried += 1
        ok, _, _ = ensure_ready(agent, inst, quick=True)
        if ok:
            woken.append((agent, inst))

    active.extend(woken)
    if len(active) < 2:
        raise RuntimeError("Not enough active agents to run a match")
    return tuple(random.sample(active, 2))  # type: ignore[return-value]


# ---------- DB write ----------
def store_matches(session: Session, league_id: int, a: Agent, b: Agent, wins_a: int, wins_b: int, draws: int) -> int:
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

    return inserted


# ---------- main ----------
def main(n_pairs: int = 1, league_id: int = LEAGUE_ID) -> None:
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
            try:
                (a, inst_a), (b, inst_b) = pick_two_ready_or_probe(session)
            except RuntimeError as e:
                print(f"❌ {e}")
                break

            print(f"🎯 Selected: {a.name} (port {inst_a.port}) vs {b.name} (port {inst_b.port})")

            try:
                footer = run_pair_with_auto_rescue(a, inst_a, b, inst_b)
            except Exception as e:
                print(f"❌ Pair crashed unexpectedly: {e}")
                footer = None

            if not footer:
                continue

            if footer["PORT_A"] != inst_a.port or footer["PORT_B"] != inst_b.port:
                print("⚠️  Port mismatch between DB and Gradle output; continuing.")

            wins_a, wins_b = footer["WINS_A"], footer["WINS_B"]
            draws, total = footer["DRAWS"], footer["TOTAL_GAMES"]

            now = datetime.datetime.now()
            inst_a.last_seen = now
            inst_b.last_seen = now
            session.commit()

            inserted = store_matches(session, league_id=league_id, a=a, b=b, wins_a=wins_a, wins_b=wins_b, draws=draws)
            session.commit()

            print(
                f"📦 Stored matches: {a.name} (wins={wins_a}) vs {b.name} (wins={wins_b}), "
                f"draws={draws}, total={total}. Inserted {inserted} rows."
            )


if __name__ == "__main__":
    main(10)
