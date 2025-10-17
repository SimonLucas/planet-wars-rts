# launch_agents_from_db.py
"""
Launch Planet Wars agents from DB with commit-scoped, collision-safe names.

Key idea: every artifact (repo dir, image, container) is uniquely identified by (agent_id, commit[:8]).
We also label images/containers and verify labels before trusting an existing container.
"""

import json
import os
import re
import socket
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from league.config import BASE_DIR
from league.init_db import get_default_db_path
from league.league_schema import Base, Agent, AgentInstance
from runner_utils.utils import run_command, find_free_port
from util.submission_evaluator_bot import load_github_token

# ---------- Config ----------
DB_PATH = get_default_db_path()
EXPOSED_INTERNAL_PORT = 8080
ENGINE = create_engine(DB_PATH)


# ---------- Small helpers ----------
def commit_short(full: Optional[str], n: int = 8) -> str:
    full = full or ""
    return full[:n] if full else "unknown"


def sanitize_image_tag(name: str) -> str:
    name = name.lower()
    name = re.sub(r'[^a-z0-9._-]+', '-', name)
    name = re.sub(r'-{2,}', '-', name).strip('-._')
    if not name:
        raise ValueError("Sanitized image tag is empty")
    return name


def ensure_executable(p: Path) -> None:
    if p.exists():
        p.chmod(p.stat().st_mode | 0o111)


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def port_is_listening(port: int, host: str = "127.0.0.1", timeout: float = 0.4) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            return True
        except OSError:
            return False


def run_capture(cmd: list[str], cwd: Optional[Path] = None) -> str:
    res = subprocess.run(
        cmd, cwd=cwd, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    return (res.stdout or "").strip()


def is_container_running(name_or_id: str) -> bool:
    try:
        out = run_capture(["podman", "inspect", "-f", "{{.State.Running}}", name_or_id])
        return out.strip().lower() == "true"
    except subprocess.CalledProcessError:
        return False


def container_exists(name_or_id: str) -> bool:
    try:
        run_capture(["podman", "inspect", name_or_id])
        return True
    except subprocess.CalledProcessError:
        return False


def get_mapped_host_port(container_name: str, container_port: int = EXPOSED_INTERNAL_PORT) -> Optional[int]:
    """
    Returns the host port mapped to container_port for the container, or None if not mapped.
    Uses `podman port <name> <port>`, which typically emits e.g. '0.0.0.0:63223' or just '63223'.
    """
    try:
        out = run_capture(["podman", "port", container_name, str(container_port)])
        last = out.splitlines()[-1].strip()
        if ":" in last:
            host_port = last.rsplit(":", 1)[-1]
        else:
            host_port = last
        port = int(host_port)
        return port if 1 <= port <= 65535 else None
    except Exception:
        return None


def get_container_id(name_or_id: str) -> Optional[str]:
    try:
        out = run_capture(["podman", "inspect", "-f", "{{.Id}}", name_or_id])
        return out.strip() or None
    except subprocess.CalledProcessError:
        return None


def get_labels(name_or_id: str) -> dict:
    try:
        out = run_capture(["podman", "inspect", "-f", "{{ json .Config.Labels }}", name_or_id])
        return json.loads(out) if out else {}
    except subprocess.CalledProcessError:
        return {}


# ---------- Deterministic, commit-scoped names ----------
def repo_dir_for(a: Agent) -> Path:
    slug = sanitize_image_tag(a.name)
    return BASE_DIR / f"{slug}-{commit_short(a.commit)}"


def image_ref_for(a: Agent) -> str:
    # repo/name must be valid; include agent_id to avoid collisions across same name
    slug = sanitize_image_tag(a.name)
    return f"pw/{slug}-{a.agent_id}:{commit_short(a.commit)}"


def container_name_for(a: Agent) -> str:
    return f"pw-agent-{a.agent_id}-{commit_short(a.commit)}"


# ---------- Stage 1: Clone ----------
def stage1_clone_repo(a: Agent, github_token: str) -> Path:
    repo_dir = repo_dir_for(a)
    if repo_dir.exists() and (repo_dir / ".git").exists():
        print(f"📂 Repo exists: {repo_dir}")
        return repo_dir

    repo_dir.parent.mkdir(parents=True, exist_ok=True)

    from urllib.parse import quote, urlparse, urlunparse
    parsed = urlparse(a.repo_url)
    authenticated = parsed._replace(netloc=f"{quote(github_token)}@{parsed.netloc}")
    clone_url = urlunparse(authenticated)

    print(f"📥 Cloning {a.repo_url} -> {repo_dir}")
    run_command(["git", "clone", clone_url, str(repo_dir)])
    return repo_dir


# ---------- Stage 2: Checkout commit ----------
def stage2_checkout_commit(a: Agent, repo_dir: Path) -> None:
    print(f"📌 Checking out {a.commit} in {repo_dir.name}")
    run_command(["git", "fetch", "--all"], cwd=repo_dir)
    run_command(["git", "checkout", a.commit], cwd=repo_dir)


# ---------- Stage 3: Build on host if needed ----------
def stage3_host_build_if_needed(repo_dir: Path) -> None:
    gradlew = repo_dir / "gradlew"
    requirements = repo_dir / "requirements.txt"
    pyproject = repo_dir / "pyproject.toml"

    if gradlew.exists():
        ensure_executable(gradlew)
        print(f"🔨 Gradle build in {repo_dir.name}")
        run_command(["./gradlew", "build"], cwd=repo_dir)
    elif requirements.exists() or pyproject.exists():
        print(f"🐍 Python project detected in {repo_dir.name} (skip host build)")
    else:
        print(f"ℹ️ No host build step detected for {repo_dir.name} (rely on image build)")


# ---------- Stage 4: Build container image ----------
def stage4_build_image(a: Agent, repo_dir: Path) -> str:
    image_ref = image_ref_for(a)

    dockerfile = None
    for candidate in ("Dockerfile", "Containerfile"):
        if (repo_dir / candidate).exists():
            dockerfile = candidate
            break

    cmd = [
        "podman", "build",
        "-t", image_ref,
        "--label", f"pw.agent_id={a.agent_id}",
        "--label", f"pw.name={a.name}",
        "--label", f"pw.commit={a.commit}",
        "--label", f"pw.repo={a.repo_url}",
        ".",
    ]
    if dockerfile:
        cmd = [
            "podman", "build",
            "-t", image_ref,
            "--label", f"pw.agent_id={a.agent_id}",
            "--label", f"pw.name={a.name}",
            "--label", f"pw.commit={a.commit}",
            "--label", f"pw.repo={a.repo_url}",
            "-f", dockerfile, ".",
        ]

    print(f"🧱 Building image {image_ref} from {repo_dir.name}")
    run_command(cmd, cwd=repo_dir)
    return image_ref


# ---------- Stage 5: Run container ----------
def stage5_run_container(a: Agent, image_ref: str, desired_port: Optional[int] = None) -> Tuple[int, str]:
    container_name = container_name_for(a)

    # Remove only THIS agent+commit container if it exists
    try:
        run_command(["podman", "rm", "-f", container_name])
    except subprocess.CalledProcessError:
        pass

    port = desired_port if (desired_port and port_is_free(desired_port)) else find_free_port()
    print(f"🚀 Running {container_name} on port {port} -> {EXPOSED_INTERNAL_PORT}")
    container_id = run_capture([
        "podman", "run", "-d",
        "-p", f"{port}:{EXPOSED_INTERNAL_PORT}",
        "--name", container_name,
        "--label", f"pw.agent_id={a.agent_id}",
        "--label", f"pw.name={a.name}",
        "--label", f"pw.commit={a.commit}",
        "--label", f"pw.repo={a.repo_url}",
        image_ref
    ])
    if not container_id:
        raise RuntimeError("Podman did not return a container ID")

    mapped = get_mapped_host_port(container_name)
    if mapped != port:
        raise RuntimeError(f"Port mapping mismatch: expected {port}, got {mapped}")

    return port, container_id


# ---------- DB upsert for AgentInstance ----------
def upsert_agent_instance(session: Session, agent_id: int, port: int, container_id: str) -> None:
    inst = session.query(AgentInstance).filter_by(agent_id=agent_id).first()
    if inst:
        inst.port = port
        inst.container_id = container_id
    else:
        session.add(AgentInstance(
            agent_id=agent_id,
            port=port,
            container_id=container_id
        ))


# ---------- Orchestrator for a single Agent row ----------
def launch_agent_for_db_agent(a: Agent, github_token: str, reuse_port: Optional[int]) -> Tuple[Path, str, int, str]:
    repo_dir = stage1_clone_repo(a, github_token)
    stage2_checkout_commit(a, repo_dir)
    stage3_host_build_if_needed(repo_dir)
    image_ref = stage4_build_image(a, repo_dir)
    port, container_id = stage5_run_container(a, image_ref, desired_port=reuse_port)
    return repo_dir, image_ref, port, container_id


# ---------- Main driver ----------
def main(limit: Optional[int] = 10, restart_existing: bool = False):
    """
    Robust launching with commit-scoped naming:
      - If an AgentInstance exists:
          * Check if its container (by recorded ID or our deterministic name) is RUNNING.
          * Verify labels match (agent_id, commit); otherwise treat as not running.
          * If running and healthy, update DB with the actual mapped port/ID if needed and skip.
          * Else, relaunch (reusing DB port if free).
      - If no AgentInstance, launch fresh.
    """
    github_token = load_github_token()
    BASE_DIR.mkdir(parents=True, exist_ok=True)

    with Session(ENGINE) as session:
        q = session.query(Agent).order_by(Agent.created_at.asc())
        if limit:
            q = q.limit(limit)
        agents = q.all()

        print(f"📋 Preparing to launch {len(agents)} agents (limit={limit})")

        for a in agents:
            container_name = container_name_for(a)
            inst = session.query(AgentInstance).filter_by(agent_id=a.agent_id).first()

            if inst:
                recorded_id = (inst.container_id or "").strip()
                recorded_port = inst.port

                # Detect running state (prefer recorded ID)
                running = False
                ident = None
                if recorded_id and container_exists(recorded_id):
                    running = is_container_running(recorded_id)
                    if running:
                        ident = recorded_id

                if not running and container_exists(container_name):
                    running = is_container_running(container_name)
                    if running:
                        ident = container_name

                # Verify labels to avoid cross-association
                if running and not restart_existing:
                    labels = get_labels(ident or container_name) or {}
                    if not (
                        labels.get("pw.agent_id") == str(a.agent_id)
                        and labels.get("pw.commit") == a.commit
                    ):
                        # Not our container; treat as not running
                        running = False

                if running and not restart_existing:
                    mapped_port = get_mapped_host_port(ident or container_name)
                    if mapped_port and port_is_listening(mapped_port):
                        # Keep DB consistent if it had stale/dummy data
                        dirty = False
                        if mapped_port != recorded_port:
                            inst.port = mapped_port
                            dirty = True

                        real_id = get_container_id(ident or container_name)
                        if real_id and real_id != recorded_id:
                            inst.container_id = real_id
                            dirty = True

                        if dirty:
                            session.commit()

                        print(f"⏭️  Skipping {a.name} (container running on port {mapped_port})")
                        continue

                # Relaunch (reuse DB port if possible and not placeholder)
                reuse_port = recorded_port if (recorded_port and port_is_free(recorded_port)) else None
                try:
                    print(f"\n🔁 Relaunching {a.name} (reuse port: {reuse_port or 'auto'})")
                    _, _, port, container_id = launch_agent_for_db_agent(
                        a, github_token, reuse_port=reuse_port
                    )
                    upsert_agent_instance(session, a.agent_id, port, container_id)
                    session.commit()
                    print(f"✅ Relaunched {a.name} @ port {port} (container {container_id[:12]})")
                except Exception as e:
                    session.rollback()
                    print(f"❌ Failed to relaunch {a.name}: {e}")

            else:
                # No instance yet: launch fresh
                try:
                    print(f"\n=== {a.name} ===")
                    _, _, port, container_id = launch_agent_for_db_agent(
                        a, github_token, reuse_port=None
                    )
                    upsert_agent_instance(session, a.agent_id, port, container_id)
                    session.commit()
                    print(f"✅ Launched {a.name} @ port {port} (container {container_id[:12]})")
                except Exception as e:
                    session.rollback()
                    print(f"❌ Failed to launch {a.name}: {e}")


if __name__ == "__main__":
    # limit=None to process all; restart_existing=True to force rebuild/restart
    main(limit=10, restart_existing=True)
