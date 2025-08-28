import os
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

# from agent_entry import AgentEntry  # your model
from runner_utils.utils import run_command, find_free_port, comment_on_issue, close_issue, \
    parse_yaml_from_issue_body  # previously defined helpers
from runner_utils.agent_entry import AgentEntry  # Assuming AgentEntry is defined in agent_entry.py
import os

from util.scan_closed_issues_for_results import load_github_token

home = Path(os.path.expanduser("~"))
KOTLIN_PROJECT_PATH = home / "GitHub/planet-wars-rts/"


def process_commit_hash(agent_data: dict) -> dict:
    """
    If agent_data["repo_url"] is a full commit URL, extract the repo base and commit hash.
    Returns a new dict with normalized repo_url and optional commit field.
    """
    new_data = agent_data.copy()

    repo_url = agent_data.get("repo_url", "")
    parsed = urlparse(repo_url)
    parts = parsed.path.strip("/").split("/")

    if "commit" in parts:
        try:
            user, repo, _, commit_hash = parts[:4]
            new_data["repo_url"] = f"https://github.com/{user}/{repo}.git"
            new_data["commit"] = commit_hash
        except Exception as e:
            raise ValueError(f"Unable to parse commit URL '{repo_url}': {e}")

    return new_data


import re

def sanitize_image_tag(name: str) -> str:
    """
    Sanitizes an arbitrary string to a valid Docker/Podman image tag.
    Rules:
    - Lowercase letters, digits, underscore, period, and dash only
    - Must start and end with alphanumeric characters
    - Disallowed characters are replaced with a dash
    - Multiple consecutive non-valid chars collapsed into a single dash
    """
    # Lowercase and replace invalid chars with '-'
    name = name.lower()
    name = re.sub(r'[^a-z0-9._-]+', '-', name)  # replace invalid chars with '-'
    name = re.sub(r'-{2,}', '-', name)          # collapse multiple dashes
    name = name.strip('-._')                    # remove leading/trailing special chars
    if not name:
        raise ValueError("Sanitized image tag is empty")
    return name

def extract_and_normalize_agent_data(issue: dict, github_token: str) -> AgentEntry | None:
    repo = "SimonLucas/planet-wars-rts-submissions"
    issue_number = issue["number"]
    body = issue["body"]

    agent_data = parse_yaml_from_issue_body(body)
    if not agent_data:
        comment_on_issue(repo, issue_number, "❌ Could not parse submission YAML.", github_token)
        return None

    agent_data = process_commit_hash(agent_data)
    agent = AgentEntry(**agent_data)
    try:
        agent.id = sanitize_image_tag(agent.id)
    except ValueError as e:
        comment_on_issue(repo, issue_number, f"❌ Invalid agent ID after sanitization: {e}", github_token)
        return None

    return agent



def clone_and_build_repo(agent: AgentEntry, base_dir: Path, github_token: str, issue_number: int) -> Path | None:
    from urllib.parse import quote, urlparse, urlunparse
    import shutil

    repo = "SimonLucas/planet-wars-rts-submissions"
    short_commit = agent.commit[:7]
    repo_dir = base_dir / f"{agent.id}-{short_commit}"

    # repo_dir = base_dir / agent.id
    gradlew_path = repo_dir / "gradlew"

    # Remove broken clone dirs
    if repo_dir.exists() and not (repo_dir / ".git").exists():
        shutil.rmtree(repo_dir)

    if not repo_dir.exists():
        parsed = urlparse(agent.repo_url)
        authenticated_netloc = f"{quote(github_token)}@{parsed.netloc}"
        authenticated_url = urlunparse(parsed._replace(netloc=authenticated_netloc))

        try:
            run_command(["git", "clone", authenticated_url, str(repo_dir)])
            comment_on_issue(repo, issue_number, "📦 Repository cloned.", github_token)
        except subprocess.CalledProcessError as e:
            comment_on_issue(repo, issue_number, f"❌ Clone failed: {e}", github_token)
            return None

    if agent.commit:
        run_command(["git", "checkout", agent.commit], cwd=repo_dir)
        comment_on_issue(repo, issue_number, f"📌 Checked out commit `{agent.commit}`", github_token)

    if not gradlew_path.exists():
        comment_on_issue(repo, issue_number, "❌ Gradle wrapper not found in repo.", github_token)
        return None

    gradlew_path.chmod(gradlew_path.stat().st_mode | 0o111)  # Ensure executable
    run_command(["./gradlew", "build"], cwd=repo_dir)
    comment_on_issue(repo, issue_number, "🔨 Project built successfully.", github_token)

    return repo_dir


def build_and_launch_container(agent: AgentEntry, repo_dir: Path, github_token: str, issue_number: int) -> int:
    short_commit = agent.commit[:7]
    container_name = f"container-{agent.id}-{short_commit}"
    image_name = f"game-server-{agent.id}-{short_commit}"

    run_command(["podman", "build", "-t", image_name, "."], cwd=repo_dir)

    try:
        run_command(["podman", "rm", "-f", container_name])
    except subprocess.CalledProcessError:
        pass

    port = find_free_port()
    run_command([
        "podman", "run", "-d",
        "-p", f"{port}:8080",
        "--name", container_name,
        image_name
    ])
    comment_on_issue("SimonLucas/planet-wars-rts-submissions", issue_number,
                     f"🚀 Agent launched at external port `{port}`.", github_token)
    return port


def run_evaluation(port: int, github_token: str, issue_number: int, timeout_seconds: int = 300) -> bool:
    repo = "SimonLucas/planet-wars-rts-submissions"
    comment_on_issue(repo, issue_number, f"🎮 Running evaluation matches...", github_token)

    try:
        subprocess.run(
            ["./gradlew", "runEvaluation", f"--args={port}"],
            cwd=KOTLIN_PROJECT_PATH,
            check=True,
            timeout=timeout_seconds,
        )
        return True
    except subprocess.TimeoutExpired:
        comment_on_issue(repo, issue_number, f"⏰ Evaluation timed out after {timeout_seconds}s.", github_token)
    except subprocess.CalledProcessError as e:
        comment_on_issue(repo, issue_number, f"❌ Evaluation failed: {e}", github_token)

    return False


def post_results(github_token: str, issue_number: int):
    md_file = Path.home() / "GitHub/planet-wars-rts/app/results/sample/league.md"
    if not md_file.exists():
        comment_on_issue("SimonLucas/planet-wars-rts-submissions", issue_number,
                         "⚠️ Evaluation completed, but results file not found.", github_token)
    else:
        markdown = md_file.read_text()
        comment_on_issue("SimonLucas/planet-wars-rts-submissions", issue_number, f"📊 **Results:**\n\n{markdown}",
                         github_token)


def stop_and_cleanup_container(agent_id: str, github_token: str, issue_number: int):
    container_name = f"container-{agent_id}"
    run_command(["podman", "stop", container_name])
    run_command(["podman", "rm", container_name])
    comment_on_issue("SimonLucas/planet-wars-rts-submissions", issue_number,
                     "✅ Evaluation complete. Stopping container.", github_token)


def process_issue(issue: dict, base_dir: Path, github_token: str, timeout_seconds: int = 600) -> bool:
    issue_number = issue["number"]

    # Step 1: Extract agent info
    agent = extract_and_normalize_agent_data(issue, github_token)
    if not agent:
        close_issue("SimonLucas/planet-wars-rts-submissions", issue_number, github_token)
        return False

    # Step 2: Clone and build repo
    comment_on_issue("SimonLucas/planet-wars-rts-submissions", issue_number,
                     f"🔍 Processing submission for `{agent.id}`", github_token)
    repo_dir = clone_and_build_repo(agent, base_dir, github_token, issue_number)
    if not repo_dir:
        close_issue("SimonLucas/planet-wars-rts-submissions", issue_number, github_token)
        return False

    # Step 3: Launch container
    try:
        port = build_and_launch_container(agent, repo_dir, github_token, issue_number)
    except Exception as e:
        comment_on_issue("SimonLucas/planet-wars-rts-submissions", issue_number,
                         f"❌ Failed to build and launch container: {e}", github_token)
        close_issue("SimonLucas/planet-wars-rts-submissions", issue_number, github_token)
        return False

    # Step 4: Run evaluation
    success = run_evaluation(port, github_token, issue_number, timeout_seconds)

    # Step 5: Report results if successful
    if success:
        post_results(github_token, issue_number)

    # Step 6: Cleanup
    try:
        stop_and_cleanup_container(agent.id, github_token, issue_number)
    except Exception as e:
        comment_on_issue("SimonLucas/planet-wars-rts-submissions", issue_number,
                         f"⚠️ Cleanup failed: {e}", github_token)

    # Step 7: Close issue
    close_issue("SimonLucas/planet-wars-rts-submissions", issue_number, github_token)

    return success
