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
                run_command(["git", "clone", authenticated_url, str(repo_dir)], timeout=60)
                print(f"📦 Cloned {agent.repo_url} into {repo_dir}")
                return True
            except subprocess.TimeoutExpired as e:
                print(f"⏱️ Clone timed out for {agent.id} (attempt {attempt + 1}): {e}")
                if attempt < retries - 1:
                    time.sleep(1.5)  # brief delay before retry
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
        # First check if the commit exists locally
        commit_exists_locally = False
        try:
            result = subprocess.run(
                ["git", "cat-file", "-e", agent.commit],
                cwd=repo_dir, capture_output=True, timeout=5
            )
            commit_exists_locally = (result.returncode == 0)
            if commit_exists_locally:
                print(f"✅ Commit {agent.commit[:8]} exists in local repo")
        except Exception:
            commit_exists_locally = False

        # Try to checkout from local repo if commit exists
        checkout_success = False
        if commit_exists_locally:
            try:
                run_command(["git", "checkout", agent.commit], cwd=repo_dir, timeout=30)
                print(f"📌 Checked out commit {agent.commit[:8]} (from local repo)")
                checkout_success = True
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                print(f"⚠️ Local checkout failed: {e}")

        # If not successful, try fetching with timeout
        if not checkout_success:
            try:
                print(f"⚙️ Fetching from origin (timeout: 30s)...")
                run_command(["git", "fetch", "origin"], cwd=repo_dir, timeout=30)
                run_command(["git", "checkout", agent.commit], cwd=repo_dir, timeout=30)
                print(f"📌 Checked out commit {agent.commit[:8]}")
                checkout_success = True
            except subprocess.TimeoutExpired as e:
                print(f"❌ Git fetch timed out after 30s: {e}")
                print(f"❌ Cannot get commit {agent.commit[:8]} - skipping this agent")
                return None
            except subprocess.CalledProcessError as e:
                print(f"❌ Git fetch/checkout failed: {e}")
                print(f"❌ Cannot get commit {agent.commit[:8]} - skipping this agent")
                return None

        if not checkout_success:
            print(f"❌ Failed to checkout requested commit {agent.commit[:8]}")
            return None

    # Ensure gradlew exists
    if not gradlew_path.exists():
        print(f"❌ Gradle wrapper not found in {repo_dir}")
        return None

    gradlew_path.chmod(gradlew_path.stat().st_mode | 0o111)
    try:
        # Use Java 22 for building to avoid Kotlin compatibility issues with newer Java versions
        import os
        build_env = os.environ.copy()
        java_22_home = "/Users/eex250/Library/Java/JavaVirtualMachines/corretto-22.0.2/Contents/Home"
        if Path(java_22_home).exists():
            build_env["JAVA_HOME"] = java_22_home
            print(f"🔧 Using Java 22 for build (JAVA_HOME={java_22_home})")
        run_command(["./gradlew", "build"], cwd=repo_dir, env=build_env)
        print(f"🔨 Build succeeded for {agent.id}")
    except subprocess.CalledProcessError as e:
        print(f"❌ Build failed for {agent.id}: {e}")
        return None

    return repo_dir
