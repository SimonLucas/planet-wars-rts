# run_agents_uniform.py
# Fair, uniform sampler across all non-quarantined agents + robust readiness +
# attempt logging for clear telemetry on underplayed agents (e.g., Python).
import os
import random
import re
import socket
import subprocess
import datetime
import time
from pathlib import Path
from typing import Optional, Tuple, List, Dict

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from league.init_db import get_default_db_path
from league.league_schema import Agent, AgentInstance, Match

# ---------- config ----------
DB_PATH = get_default_db_path()
ENGINE = create_engine(DB_PATH)
GAMES_PER_PAIR = 10

# Be kind to Python I/O: 200 ms per remote RPC (was 50 ms)
REMOTE_TIMEOUT = 200  # ms per remote RPC call

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


from typing import List, Tuple  # noqa: E402


def _run_podman(args: List[str], timeout: int) -> Tuple[int, str, str]:
    """
    Wrapper that injects '--log-driver=none' for 'podman run'/'create'
    to prevent container stdout/stderr from flooding journald/syslog.

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
            # If you prefer rotated file logs instead:
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
    """
    Ensures the agent is reachable on its port, optionally attempting to start/restart the container.
    quick=True uses a short wait (HEAL_WAIT_SECS); quick=False uses START_WAIT_SECS.
    """
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
    re.compile(r"Channel was cancelled", re.I),
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


# ---------- attempt logging ----------
def record_match_attempt(session: Session, agent_a_id: int, agent_b_id: int,
                         result: str, error: Optional[str] = None, retried: int = 0) -> None:
    """
    Persist a lightweight attempt log so we can distinguish scheduling bias vs. runtime failures.
    result ∈ {'completed','failed'}
    retried: 0/1 flag indicating whether we did one auto-rescue restart.
    """
    session.execute(text("""
        CREATE TABLE IF NOT EXISTS match_attempt (
            attempt_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            ts           DATETIME NOT NULL,
            agent_a_id   INTEGER NOT NULL,
            agent_b_id   INTEGER NOT NULL,
            result       TEXT NOT NULL,
            error        TEXT,
            retried      INTEGER NOT NULL DEFAULT 0
        )
    """))
    session.execute(
        text("""
            INSERT INTO match_attempt (ts, agent_a_id, agent_b_id, result, error, retried)
            VALUES (:ts, :a, :b, :r, :e, :ret)
        """),
        {
            "ts": datetime.datetime.now(),
            "a": agent_a_id,
            "b": agent_b_id,
            "r": result,
            "e": (error or "")[:1000],
            "ret": int(retried),
        }
    )
    session.commit()


# ---------- run one evaluation ----------
def run_remote_pair_evaluation(port_a: int, port_b: int, games_per_pair: int, timeout_ms: int) -> Tuple[
    bool, Optional[dict], str]:
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


def run_pair_with_auto_rescue(a: Agent, inst_a: AgentInstance, b: Agent, inst_b: AgentInstance) -> Tuple[
    Optional[dict], Optional[str], int]:
    """
    Returns: (footer_or_none, error_text_or_none, retried_flag)
    retried_flag ∈ {0,1}
    """
    ok_a, ident_a, port_a = ensure_ready(a, inst_a, quick=False)
    ok_b, ident_b, port_b = ensure_ready(b, inst_b, quick=False)
    if not (ok_a and ok_b):
        msg = f"Not ready after full wait: {a.name if not ok_a else ''} {b.name if not ok_b else ''}".strip()
        print(f"⛔ {msg}")
        return None, msg, 0

    ok, footer, text_blob = run_remote_pair_evaluation(port_a, port_b, GAMES_PER_PAIR, REMOTE_TIMEOUT)
    if ok:
        return footer, None, 0

    if not is_retryable_ws_error(text_blob):
        print(f"❌ Pair failed (no retry):\n{text_blob}")
        return None, text_blob, 0

    print("🔁 WebSocket closed/cancelled mid-run; restarting both and retrying once…")
    if ident_a:
        restart_container(ident_a)
    if ident_b:
        restart_container(ident_b)

    if not wait_for_port(port_a, timeout=START_WAIT_SECS) or not wait_for_port(port_b, timeout=START_WAIT_SECS):
        msg = "Ports not ready after restart; giving up on this pair."
        print(f"⛔ {msg}")
        _quarantine(a.agent_id);
        _quarantine(b.agent_id)
        return None, msg, 1

    ok2, footer2, text_blob2 = run_remote_pair_evaluation(port_a, port_b, GAMES_PER_PAIR, REMOTE_TIMEOUT)
    if ok2:
        return footer2, None, 1

    # Still failed: quarantine both agents briefly
    if is_retryable_ws_error(text_blob2):
        print("🧯 Retry hit another transient WS error; quarantining both agents for a bit.")
        _quarantine(a.agent_id);
        _quarantine(b.agent_id)
    print(f"❌ Retry failed:\n{text_blob2}")
    return None, text_blob2, 1


# ---------- selection (uniform & fair) ----------
def _rows_with_instances(session: Session) -> List[Tuple[Agent, AgentInstance]]:
    return (
        session.query(Agent, AgentInstance)
        .join(AgentInstance, Agent.agent_id == AgentInstance.agent_id)
        .all()
    )


def pick_two_uniform_nonquarantined(session: Session) -> Tuple[
    Tuple[Agent, AgentInstance], Tuple[Agent, AgentInstance]]:
    """
    Strictly uniform sampling from all agents that (a) have an instance and (b) are not quarantined.
    We DON'T do quick readiness checks here — fairness first, readiness later.
    """
    rows = _rows_with_instances(session)
    pool: List[Tuple[Agent, AgentInstance]] = [
        (a, inst)
        for (a, inst) in rows
        if not _is_quarantined(a.agent_id) and inst.port != 123  # keep your sentinel exclusion
    ]
    if len(pool) < 2:
        raise RuntimeError("Not enough eligible agents to run a match")
    return tuple(random.sample(pool, 2))  # type: ignore[return-value]


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

    # If you later support draws, you can add rows here with winner_id=None and scores 0.5/0.5 or similar.

    return inserted


# ---------- main ----------
def main(n_pairs: int = 10, league_id: int = LEAGUE_ID) -> None:
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
                (a, inst_a), (b, inst_b) = pick_two_uniform_nonquarantined(session)
            except RuntimeError as e:
                print(f"❌ {e}")
                break

            # paranoia: should never happen with random.sample
            if a.agent_id == b.agent_id:
                print("⚠️  Self-match detected; retrying selection.")
                continue

            print(f"🎯 Selected: {a.name} (port {inst_a.port}) vs {b.name} (port {inst_b.port})")

            try:
                footer, err, retried = run_pair_with_auto_rescue(a, inst_a, b, inst_b)
            except Exception as e:
                err = f"Pair crashed unexpectedly: {type(e).__name__}: {e}"
                footer, retried = None, 0
                print(f"❌ {err}")

            # Log attempt result (completed/failed)
            if footer:
                record_match_attempt(session, a.agent_id, b.agent_id, result="completed", error=None, retried=retried)
            else:
                record_match_attempt(session, a.agent_id, b.agent_id, result="failed", error=err, retried=retried)
                continue  # nothing to store in Matches

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
    # Default to 10 pairs per invocation, mirroring your previous script behavior.
    main(10)
