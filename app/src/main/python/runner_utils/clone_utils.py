from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urlunparse, quote
import subprocess
import shutil
import time

from runner_utils.agent_entry import AgentEntry
from runner_utils.utils import run_command


def robust_clone_and_build(agent: AgentEntry, base_dir: Path, github_token: str) -> Optional[Path]:
    agent.id = agent.id.lower().strip()
    repo_dir = base_dir / agent.id
    gradlew_path = repo_dir / "gradlew"

    # Early cleanup of incomplete repo
    if repo_dir.exists() and not (repo_dir / ".git").exists():
        print(f"⚠️ Removing incomplete repo at {repo_dir}")
        shutil.rmtree(repo_dir)

    # Validate URL
    if "/commit/" in agent.repo_url:
        print(f"❌ Invalid repo_url: {agent.repo_url} – must be a Git repo URL, not a commit link.")
        return None

    # Prepare authenticated clone URL
    parsed = urlparse(agent.repo_url)
    authenticated_netloc = f"{quote(github_token)}@{parsed.netloc}"
    authenticated_url = str(urlunparse(parsed._replace(netloc=authenticated_netloc)))

    def do_clone(retries: int = 2) -> bool:
        for attempt in range(retries):
            try:
                run_command(["git", "clone", authenticated_url, str(repo_dir)])
                print(f"📦 Cloned {agent.repo_url} into {repo_dir}")
                return True
            except subprocess.CalledProcessError as e:
                print(f"❌ Clone failed for {agent.id} (attempt {attempt + 1}): {e}")
                if attempt < retries - 1:
                    time.sleep(1.5)  # brief delay before retry
        return False

    # Clone if needed
    if not repo_dir.exists():
        if not do_clone():
            return None

    # Attempt commit checkout
    if agent.commit:
        try:
            run_command(["git", "fetch", "origin"], cwd=repo_dir)
            run_command(["git", "checkout", agent.commit], cwd=repo_dir)
            print(f"📌 Checked out commit {agent.commit}")
        except subprocess.CalledProcessError as e:
            print(f"⚠️ Checkout failed — cleaning repo and retrying clone: {e}")
            shutil.rmtree(repo_dir)
            if not do_clone():
                return None
            try:
                run_command(["git", "fetch", "origin"], cwd=repo_dir)
                run_command(["git", "checkout", agent.commit], cwd=repo_dir)
                print(f"📌 Retried and checked out commit {agent.commit}")
            except subprocess.CalledProcessError as e:
                print(f"❌ Retry checkout failed for {agent.id}: {e}")
                return None

    # Ensure gradlew exists
    if not gradlew_path.exists():
        print(f"❌ Gradle wrapper not found in {repo_dir}")
        return None

    gradlew_path.chmod(gradlew_path.stat().st_mode | 0o111)
    try:
        run_command(["./gradlew", "build"], cwd=repo_dir)
        print(f"🔨 Build succeeded for {agent.id}")
    except subprocess.CalledProcessError as e:
        print(f"❌ Build failed for {agent.id}: {e}")
        return None

    return repo_dir
