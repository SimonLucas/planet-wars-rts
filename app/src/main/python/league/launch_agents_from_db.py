# launch_agents_from_db.py
import os
import re
import socket
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from league.init_db import get_default_db_path
from league_schema import Base, Agent, AgentInstance
from runner_utils.agent_entry import AgentCommitEntry
from runner_utils.utils import run_command, find_free_port

# ---------- Config ----------
DB_PATH = get_default_db_path()
BASE_DIR = Path.home() / "cog-runs" / "agents"
EXPOSED_INTERNAL_PORT = 8080
ENGINE = create_engine(DB_PATH)


# ---------- Small helpers ----------
def short_hash(full: str) -> str:
    return full[:7] if full else "unknown"


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


def is_container_running(name_or_id: str) -> bool:
    """
    Return True iff a container with the given ID or name exists and is running.
    """
    try:
        out = run_command(["podman", "inspect", "-f", "{{.State.Running}}", name_or_id])
        return out.strip().lower() == "true"
    except subprocess.CalledProcessError:
        return False


def container_exists(name_or_id: str) -> bool:
    try:
        run_command(["podman", "inspect", name_or_id])
        return True
    except subprocess.CalledProcessError:
        return False


# ---------- Stage 1: Clone ----------
def stage1_clone_repo(agent: AgentCommitEntry, base_dir: Path, github_token: str) -> Path:
    """
    Clone into <id>-<short> so multiple commits can coexist.
    """
    repo_dir = base_dir / f"{sanitize_image_tag(agent.id)}-{short_hash(agent.commit)}"
    if repo_dir.exists() and (repo_dir / ".git").exists():
        print(f"📂 Repo exists: {repo_dir}")
        return repo_dir

    repo_dir.parent.mkdir(parents=True, exist_ok=True)

    from urllib.parse import quote, urlparse, urlunparse
    parsed = urlparse(agent.repo_url)
    authenticated = parsed._replace(netloc=f"{quote(github_token)}@{parsed.netloc}")
    clone_url = urlunparse(authenticated)

    print(f"📥 Cloning {agent.repo_url} -> {repo_dir}")
    run_command(["git", "clone", clone_url, str(repo_dir)])
    return repo_dir


# ---------- Stage 2: Checkout commit ----------
def stage2_checkout_commit(agent: AgentCommitEntry, repo_dir: Path) -> None:
    print(f"📌 Checking out {agent.commit} in {repo_dir.name}")
    run_command(["git", "fetch", "--all"], cwd=repo_dir)
    run_command(["git", "checkout", agent.commit], cwd=repo_dir)


# ---------- Stage 3: Build on host if needed ----------
def stage3_host_build_if_needed(repo_dir: Path) -> None:
    """
    If gradlew exists -> ./gradlew build.
    Python projects (requirements/pyproject) skip host build; handle in image.
    Otherwise, rely on container build step.
    """
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
def stage4_build_image(agent: AgentCommitEntry, repo_dir: Path) -> str:
    image_name = f"game-server-{sanitize_image_tag(agent.id)}"
    dockerfile = None
    for candidate in ("Dockerfile", "Containerfile"):
        if (repo_dir / candidate).exists():
            dockerfile = candidate
            break

    cmd = ["podman", "build", "-t", image_name, "."]
    if dockerfile:
        cmd = ["podman", "build", "-t", image_name, "-f", dockerfile, "."]

    print(f"🧱 Building image {image_name} from {repo_dir.name}")
    run_command(cmd, cwd=repo_dir)
    return image_name


# ---------- Stage 5: Run container ----------
def stage5_run_container(agent: AgentCommitEntry, image_name: str, desired_port: Optional[int] = None) -> Tuple[int, str]:
    """
    Run the image, publishing a host port -> 8080 in the container.
    If desired_port is provided and free, use it; otherwise pick a free one.
    Returns (port, container_id).
    """
    container_name = f"container-{sanitize_image_tag(agent.id)}"

    # Clean prior container if exists (any state)
    try:
        run_command(["podman", "rm", "-f", container_name])
    except subprocess.CalledProcessError:
        pass

    port = desired_port if (desired_port and port_is_free(desired_port)) else find_free_port()
    print(f"🚀 Running {container_name} on port {port} -> {EXPOSED_INTERNAL_PORT}")
    container_id = run_command([
        "podman", "run", "-d",
        "-p", f"{port}:{EXPOSED_INTERNAL_PORT}",
        "--name", container_name,
        image_name
    ])
    if not container_id:
        raise RuntimeError("Podman did not return a container ID")

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
def launch_agent_for_db_agent(db_agent: Agent, base_dir: Path, github_token: str, reuse_port: Optional[int]) -> Tuple[Path, str, int, str]:
    """
    Builds and runs the container for a DB Agent row.
    Optionally reuses a specific host port (if free).
    Returns (repo_dir, image_name, port, container_id).
    """
    agent = AgentCommitEntry(
        id=db_agent.name,           # already sanitized + short hash appended
        repo_url=db_agent.repo_url, # root .git URL
        commit=db_agent.commit      # full (preferred) or short hash
    )

    repo_dir = stage1_clone_repo(agent, base_dir, github_token)
    stage2_checkout_commit(agent, repo_dir)
    stage3_host_build_if_needed(repo_dir)
    image_name = stage4_build_image(agent, repo_dir)
    port, container_id = stage5_run_container(agent, image_name, desired_port=reuse_port)
    return repo_dir, image_name, port, container_id


# ---------- Main driver ----------
def main(limit: Optional[int] = None, restart_existing: bool = False):
    """
    - Reads Agents from DB (ordered by created_at)
    - For each, checks AgentInstance:
        - If no instance: launch & create row
        - If exists:
            - If container is running (by ID or name) -> skip (unless restart_existing=True)
            - If not running -> relaunch (reuse the recorded port if possible) & update row
    """
    from util.submission_evaluator_bot import load_github_token
    github_token = load_github_token()

    BASE_DIR.mkdir(parents=True, exist_ok=True)

    with Session(ENGINE) as session:
        q = session.query(Agent).order_by(Agent.created_at.asc())
        if limit:
            q = q.limit(limit)
        agents = q.all()

        print(f"📋 Preparing to launch {len(agents)} agents")

        for a in agents:
            container_name = f"container-{sanitize_image_tag(a.name)}"
            inst = session.query(AgentInstance).filter_by(agent_id=a.agent_id).first()

            # Decide whether to skip/restart/relaunch
            if inst:
                recorded_id = (inst.container_id or "").strip()
                recorded_port = inst.port

                running = False
                # Prefer checking by ID if we have one
                if recorded_id:
                    running = is_container_running(recorded_id)
                # Fallback: check by deterministic name
                if not running and container_exists(container_name):
                    running = is_container_running(container_name)

                if running and not restart_existing:
                    print(f"⏭️  Skipping {a.name} (container running on port {recorded_port})")
                    continue

                # Not running or forced restart: relaunch
                reuse_port = recorded_port if recorded_port and port_is_free(recorded_port) else None
                try:
                    print(f"\n🔁 Relaunching {a.name} (reuse port: {reuse_port or 'auto'})")
                    repo_dir, image_name, port, container_id = launch_agent_for_db_agent(
                        a, BASE_DIR, github_token, reuse_port=reuse_port
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
                    repo_dir, image_name, port, container_id = launch_agent_for_db_agent(
                        a, BASE_DIR, github_token, reuse_port=None
                    )
                    upsert_agent_instance(session, a.agent_id, port, container_id)
                    session.commit()
                    print(f"✅ Launched {a.name} @ port {port} (container {container_id[:12]})")
                except Exception as e:
                    session.rollback()
                    print(f"❌ Failed to launch {a.name}: {e}")


if __name__ == "__main__":
    # limit=None to process all; restart_existing=True to force rebuild/restart
    main(limit=None, restart_existing=False)
