import re
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, List
import os
import requests

from github import Github
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from league.init_db import get_default_db_path
from runner_utils.agent_entry import AgentEntry, AgentCommitEntry, to_agent_commit_entry
from runner_utils.utils import (
    find_free_port,
    parse_yaml_from_issue_body,
    comment_on_issue,
)
from league.league_schema import Base, Agent, AgentInstance, Rating
from util.submission_evaluator_bot import load_github_token

# Config
REPO = "SimonLucas/planet-wars-rts-submissions"
DB_PATH = get_default_db_path()


def run_command(cmd: List[str], cwd: Optional[Path] = None) -> str:
    redacted_cmd = [re.sub(r'(https://)([^:@]+)(@github\.com)', r'\1***REDACTED***\3', arg) for arg in cmd]
    print(f"🔧 Running entry: {' '.join(redacted_cmd)} (in {cwd or Path.cwd()})")
    result = subprocess.run(cmd, check=True, cwd=cwd, capture_output=True, text=True)
    return result.stdout.strip()


from runner_utils.agent_entry import AgentEntry, AgentCommitEntry, to_agent_commit_entry


def extract_successful_issues(repo: str, github_token: str, limit: Optional[int] = None) -> List[Tuple[int, AgentCommitEntry, float]]:
    g = Github(github_token)
    gh_repo = g.get_repo(repo)

    # Fetch all closed issues (don't restrict by label!)
    issues = gh_repo.get_issues(state="closed")
    print(f"🔍 Scanning {issues.totalCount} closed issues in {repo}")

    successful = []

    for issue in issues:
        if limit is not None and len(successful) >= limit:
            break

        issue_number = issue.number
        body = issue.body
        agent_data = parse_yaml_from_issue_body(body)

        if not agent_data:
            print(f"❌ Skipping issue #{issue_number}: could not parse YAML")
            continue

        comments = list(issue.get_comments())
        result_comment = next((c for c in reversed(comments) if "AVG=" in c.body), None)

        # result_comment = next((c for c in reversed(comments) if "AVG=" in c.body), None)

        agent_entry = AgentEntry(**agent_data)
        agent = to_agent_commit_entry(agent_entry)
        print()
        print(f"🔍 Processing issue #{issue_number} with agent commit data: {agent}")

        if not result_comment:
            print(f"❌ Skipping issue #{issue_number}: no result comment found")
            continue

        avg_match = re.search(r"AVG\s*=\s*([\d.]+)", result_comment.body)
        if not avg_match:
            print(f"❌ Skipping issue #{issue_number}: no AVG= found in comment")
            continue

        try:
            avg_score = float(avg_match.group(1))
            print(f"✅ Issue #{issue_number}: {agent.id} @ {agent.commit}")
            successful.append((issue_number, agent, avg_score))
        except Exception as e:
            print(f"❌ Skipping issue #{issue_number}: , with agent data {agent_data} - "
                  f"error creating AgentCommitEntry: {e}")

    return successful


def register_in_db(agent: AgentCommitEntry, port: int, container_id: str, db_path: str = DB_PATH):
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
        session.close()
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
    # SUBMISSION_DIR.mkdir(parents=True, exist_ok=True)

    successful = extract_successful_issues(REPO, github_token, limit)
    print(f"📋 Found {len(successful)} successful submissions to process.")

    for issue_number, agent, avg in successful:
        try:
            print(f"🚀 Registering {agent.id} from issue #{issue_number}")
            port, container_id = 123, "99"  # Placeholder
            register_in_db(agent, port, container_id)
        except Exception as e:
            print(f"❌ Failed to register {agent.id} from issue #{issue_number}: {e}")


if __name__ == "__main__":
    main(limit=20)
