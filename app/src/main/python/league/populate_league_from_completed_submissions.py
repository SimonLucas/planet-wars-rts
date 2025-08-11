import re
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, List

from github import Github
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from league.init_db import get_default_db_path
from runner_utils.agent_entry import AgentEntry
from runner_utils.utils import (
    find_free_port,
    parse_yaml_from_issue_body, comment_on_issue,
)
from league_schema import Base, Agent, AgentInstance, Rating
from util.submission_evaluator_bot import load_github_token
from runner_utils.process_issue import sanitize_image_tag, clone_and_build_repo

from urllib.parse import urlparse

# Config
REPO = "SimonLucas/planet-wars-rts-submissions"
DB_PATH = get_default_db_path()
SUBMISSION_DIR = Path.home() / "cog-runs" / "submissions"

def run_command(cmd: List[str], cwd: Optional[Path] = None) -> str:
    redacted_cmd = [re.sub(r'(https://)([^:@]+)(@github\.com)', r'\1***REDACTED***\3', arg) for arg in cmd]
    print(f"🔧 Running entry: {' '.join(redacted_cmd)} (in {cwd or Path.cwd()})")

    result = subprocess.run(cmd, check=True, cwd=cwd, capture_output=True, text=True)
    return result.stdout.strip()

import os
import re
import requests

def process_commit_hash(agent_data: dict) -> dict:
    """
    Normalize repo_url and extract or fetch commit hash.

    Priority:
    1. Use provided `commit` field.
    2. Else extract from `repo_url` if it's a commit URL.
    3. Else call GitHub API to get latest commit from default branch.
    """
    new_data = agent_data.copy()

    raw_url = new_data.get("repo_url", "").strip().rstrip("/")

    # Step 1: Normalize the repo URL to root
    repo_match = re.match(r"(https://github\.com/[^/]+/[^/]+)", raw_url)
    if not repo_match:
        raise ValueError(f"Invalid or missing GitHub repo URL: {raw_url}")

    root_url = f"{repo_match.group(1)}.git"
    new_data["repo_url"] = root_url

    # Step 2: Use provided commit if available
    if "commit" in new_data and new_data["commit"]:
        return new_data

    # Step 3: Try extracting from /commit/<hash> in URL
    commit_match = re.search(r"/commit/([a-f0-9]{7,40})", raw_url)
    if commit_match:
        new_data["commit"] = commit_match.group(1)
        return new_data

    # Step 4: Call GitHub API to get latest commit from default branch
    gh_token = os.environ.get("GITHUB_TOKEN")
    if not gh_token:
        raise RuntimeError("Missing GITHUB_TOKEN in environment")

    headers = {"Authorization": f"Bearer {gh_token}"}
    api_repo_match = re.match(r"https://github\.com/([^/]+/[^/.]+)", raw_url)
    if not api_repo_match:
        raise ValueError(f"Could not parse repo for API lookup: {raw_url}")

    repo_path = api_repo_match.group(1)

    try:
        # Get default branch
        repo_info = requests.get(
            f"https://api.github.com/repos/{repo_path}",
            headers=headers
        ).json()
        default_branch = repo_info.get("default_branch", "main")

        # Get latest commit from default branch
        branch_info = requests.get(
            f"https://api.github.com/repos/{repo_path}/commits/{default_branch}",
            headers=headers
        ).json()

        full_commit = branch_info["sha"]
        new_data["commit"] = full_commit
        return new_data
    except Exception as e:
        raise RuntimeError(f"Failed to fetch commit hash from GitHub for {repo_path}: {e}")

def build_and_launch_container(agent: AgentEntry, repo_dir: Path, github_token: str, issue_number: int) -> Tuple[int, str]:
    container_name = f"container-{agent.id}"
    image_name = f"game-server-{agent.id}"

    run_command(["podman", "build", "-t", image_name, "."], cwd=repo_dir)

    try:
        run_command(["podman", "rm", "-f", container_name])
    except subprocess.CalledProcessError:
        pass

    port = find_free_port()
    container_id = run_command([
        "podman", "run", "-d",
        "-p", f"{port}:8080",
        "--name", container_name,
        image_name
    ])

    if not container_id:
        raise RuntimeError("❌ Podman did not return a container ID!")

    comment_on_issue(REPO, issue_number,
                     f"🚀 Agent launched at external port `{port}`.", github_token)
    return port, container_id

def extract_successful_issues(repo: str, github_token: str, limit: Optional[int] = None) -> List[Tuple[int, dict, float]]:
    g = Github(github_token)
    gh_repo = g.get_repo(repo)
    issues = gh_repo.get_issues(state="closed", labels=["completed"])

    print(f"🔍 Found {issues.totalCount} closed issues with 'completed' label in {repo}")

    successful = []

    for issue in issues:
        if limit is not None and len(successful) >= limit:
            break
        issue_number = issue.number
        comments = issue.get_comments()
        result_comment = next((c for c in comments if "AVG=" in c.body), None)
        if not result_comment:
            continue

        avg_match = re.search(r"AVG\s*=\s*([\d.]+)", result_comment.body)
        if not avg_match:
            continue

        avg_score = float(avg_match.group(1))
        body = issue.body
        agent_data = parse_yaml_from_issue_body(body)
        if not agent_data:
            print(f"❌ Could not parse YAML for issue #{issue_number}")
            continue

        successful.append((issue_number, agent_data, avg_score))
        print(f"✅ Found successful submission (issue #{issue_number})")

    return successful

def register_in_db(agent: AgentEntry, port: int, container_id: str, db_path: str = DB_PATH):
    engine = create_engine(db_path)
    Base.metadata.create_all(engine)
    session = Session(engine)

    existing_agent = session.query(Agent).filter_by(
        name=agent.id,
        repo_url=agent.repo_url,
        commit=agent.commit
    ).first()

    if existing_agent:
        print(f"⚠️ Agent {agent.id} at commit {agent.commit} already in DB, skipping")
        return

    new_agent = Agent(
        name=agent.id,
        owner="unknown",
        repo_url=agent.repo_url,
        commit=agent.commit,
        created_at=datetime.now()
    )
    session.add(new_agent)
    session.flush()  # Assigns agent_id

    session.add(Rating(
        agent_id=new_agent.agent_id,
        league_id=1,
        mu=25.0,
        sigma=8.333,
        updated_at=datetime.now()
    ))

    session.add(AgentInstance(
        agent_id=new_agent.agent_id,
        port=port,
        container_id=container_id,
        last_seen=datetime.now()
    ))

    session.commit()
    session.close()
    print(f"📝 Registered {agent.id} in DB (port {port})")

def main(limit: Optional[int] = None):
    github_token = load_github_token()
    SUBMISSION_DIR.mkdir(parents=True, exist_ok=True)

    successful = extract_successful_issues(REPO, github_token, limit)
    print(f"Found {len(successful)} successful submissions to process.")

    for issue_number, agent_data, avg in successful:
        try:
            print(f"🚀 Processing {agent_data.get('id', '?')} (issue #{issue_number})")

            # Use unprocessed agent to clone repo
            tmp_agent = AgentEntry(**agent_data)

            short_hash = tmp_agent.commit[:7] if tmp_agent.commit else "unknown"
            tmp_agent.id = sanitize_image_tag(f"{tmp_agent.id}-{short_hash}")


            # repo_dir = clone_and_build_repo(tmp_agent, SUBMISSION_DIR, github_token, issue_number)

            # Now extract the actual commit from repo
            updated_data = process_commit_hash(agent_data)
            agent = AgentEntry(**updated_data)
            agent.id = sanitize_image_tag(agent.id)

            print(f"🔗 Testing repo for {agent.id} at commit {agent.commit}")

            # port, container_id = build_and_launch_container(agent, repo_dir, github_token, issue_number)
            port, container_id = 123, "99"  # Placeholder for actual port/container ID logic
            register_in_db(agent, port, container_id)

        except Exception as e:
            print(f"❌ Failed to launch/register {agent_data.get('id', '?')}: {e}")

if __name__ == "__main__":
    main(limit=10)
