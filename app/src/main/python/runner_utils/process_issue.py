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

def detect_project_type(repo_dir: Path) -> tuple[str, bool]:
    """
    Detect whether this is a Kotlin/Java or Python project by examining the Dockerfile.
    The Dockerfile is the source of truth for how to build the submission.
    Returns: (project_type, needs_pre_build)
      - project_type: 'gradle', 'python', 'dockerfile-only', or 'unknown'
      - needs_pre_build: True if we need to run gradle/pip before Docker build
    """
    print(f"🔍 [v4.0] Detecting project type in: {repo_dir}")
    print(f"  - gradlew exists: {(repo_dir / 'gradlew').exists()}")
    print(f"  - requirements.txt exists: {(repo_dir / 'requirements.txt').exists()}")
    print(f"  - pyproject.toml exists: {(repo_dir / 'pyproject.toml').exists()}")
    print(f"  - Dockerfile exists: {(repo_dir / 'Dockerfile').exists()}")

    # Check Dockerfile first - it's the source of truth
    dockerfile_path = repo_dir / "Dockerfile"
    if dockerfile_path.exists():
        try:
            dockerfile_content = dockerfile_path.read_text().lower()
            print(f"  📄 Reading Dockerfile to determine build requirements...")

            # Check if Dockerfile is self-contained (multi-stage build)
            has_multistage = 'as builder' in dockerfile_content or 'as build' in dockerfile_content
            has_gradle_in_docker = 'from gradle' in dockerfile_content or 'run gradle' in dockerfile_content or 'run ./gradlew' in dockerfile_content

            # Check if Dockerfile expects pre-built artifacts
            expects_prebuilt_jar = 'copy app/build/libs/' in dockerfile_content
            expects_prebuilt_python = False  # Python typically doesn't need pre-build

            # Look for Python indicators
            python_indicators = ['pip install', 'requirements.txt', 'python', 'pyproject.toml', 'poetry']
            has_python = any(indicator in dockerfile_content for indicator in python_indicators)

            # Look for Gradle indicators
            gradle_indicators = ['gradle', './gradlew', 'build.gradle']
            has_gradle_ref = any(indicator in dockerfile_content for indicator in gradle_indicators)

            print(f"  - Dockerfile multi-stage build: {has_multistage}")
            print(f"  - Dockerfile has gradle build: {has_gradle_in_docker}")
            print(f"  - Dockerfile expects pre-built JAR: {expects_prebuilt_jar}")
            print(f"  - Dockerfile contains Python indicators: {has_python}")

            # Determine type and whether pre-build is needed
            if has_python:
                detected = "python"
                needs_pre_build = False  # Python submissions are self-contained
            elif has_gradle_in_docker:
                detected = "gradle-self-contained"
                needs_pre_build = False  # Dockerfile handles gradle build
            elif expects_prebuilt_jar and (repo_dir / "gradlew").exists():
                detected = "gradle-legacy"
                needs_pre_build = True  # Old style: needs gradle build before Docker
            elif has_gradle_ref:
                detected = "gradle"
                needs_pre_build = False  # Assume self-contained if not clearly legacy
            else:
                detected = "dockerfile-only"
                needs_pre_build = False

        except Exception as e:
            print(f"  ⚠️ Could not read Dockerfile: {e}")
            # Fallback to file-based detection
            if (repo_dir / "gradlew").exists():
                detected = "gradle-legacy"
                needs_pre_build = True
            elif (repo_dir / "requirements.txt").exists() or (repo_dir / "pyproject.toml").exists():
                detected = "python"
                needs_pre_build = False
            else:
                detected = "dockerfile-only"
                needs_pre_build = False
    else:
        # No Dockerfile - this will likely fail validation later
        detected = "unknown"
        needs_pre_build = False

    print(f"  ✅ Detected type: {detected}, needs pre-build: {needs_pre_build}")
    return detected, needs_pre_build


def validate_submission(repo_dir: Path, project_type: str) -> tuple[bool, str]:
    """
    Validate that submission has required files.
    Returns: (is_valid, error_message)
    """
    if not (repo_dir / "Dockerfile").exists():
        return False, "Missing Dockerfile"

    # Check Dockerfile exposes port 8080
    try:
        dockerfile_content = (repo_dir / "Dockerfile").read_text()
        if "EXPOSE 8080" not in dockerfile_content and "8080" not in dockerfile_content:
            return False, "Dockerfile must expose port 8080"
    except Exception as e:
        return False, f"Could not read Dockerfile: {e}"

    return True, "OK"


def build_project(repo_dir: Path, project_type: str, needs_pre_build: bool, github_token: str, issue_number: int) -> bool:
    """
    Build the project based on its type.
    Supports both legacy (pre-build) and modern (self-contained Dockerfile) submissions.
    Returns: True if build succeeded, False otherwise
    """
    repo = "SimonLucas/planet-wars-rts-submissions"
    print(f"🔨 [v4.0] Processing project with type: {project_type}, needs_pre_build: {needs_pre_build}")

    # Validate Dockerfile exists
    is_valid, error_msg = validate_submission(repo_dir, project_type)
    if not is_valid:
        comment_on_issue(repo, issue_number, f"❌ Validation failed: {error_msg}", github_token)
        return False

    if needs_pre_build:
        # Legacy mode: Run gradle build before Docker build (backward compatibility)
        comment_on_issue(repo, issue_number,
            f"📦 Detected **{project_type}** project (legacy mode). Running pre-build...", github_token)

        gradlew_path = repo_dir / "gradlew"
        if not gradlew_path.exists():
            comment_on_issue(repo, issue_number, "❌ Gradle wrapper not found for legacy build.", github_token)
            return False

        gradlew_path.chmod(gradlew_path.stat().st_mode | 0o111)  # Ensure executable

        # Try gradle build with retry on cache corruption
        max_retries = 2
        for attempt in range(max_retries):
            try:
                # Use --no-daemon to avoid daemon-related cache issues
                run_command(["./gradlew", "build", "--no-daemon"], cwd=repo_dir)
                comment_on_issue(repo, issue_number,
                    "🔨 Pre-build completed. Docker will use pre-built artifacts.", github_token)
                return True
            except subprocess.CalledProcessError as e:
                error_msg = str(e)
                # Check if it's a cache corruption issue
                if "workspace metadata" in error_msg or "metadata.bin" in error_msg:
                    if attempt < max_retries - 1:
                        print(f"⚠️ Gradle cache corruption detected. Cleaning and retrying... (attempt {attempt + 1}/{max_retries})")
                        comment_on_issue(repo, issue_number,
                            "⚠️ Gradle cache issue detected. Cleaning cache and retrying...", github_token)
                        # Clean the specific gradle project cache
                        try:
                            run_command(["./gradlew", "clean", "--no-daemon"], cwd=repo_dir)
                        except:
                            pass
                    else:
                        comment_on_issue(repo, issue_number,
                            f"❌ Pre-build failed after {max_retries} attempts due to Gradle cache corruption. Please clear your Gradle cache: `rm -rf ~/.gradle/caches`", github_token)
                        return False
                else:
                    comment_on_issue(repo, issue_number, f"❌ Pre-build failed: {e}", github_token)
                    return False

        return False
    else:
        # Modern mode: Self-contained Dockerfile handles everything
        comment_on_issue(repo, issue_number,
            f"📦 Detected **{project_type}** project (self-contained). Docker will handle all building.", github_token)
        comment_on_issue(repo, issue_number, "✅ Validation passed.", github_token)
        return True


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

    # Remove broken clone dirs
    if repo_dir.exists() and not (repo_dir / ".git").exists():
        shutil.rmtree(repo_dir)

    if not repo_dir.exists():
        parsed = urlparse(agent.repo_url)
        authenticated_netloc = f"{quote(github_token)}@{parsed.netloc}"
        authenticated_url = urlunparse(parsed._replace(netloc=authenticated_netloc))

        try:
            run_command(["git", "clone", authenticated_url, str(repo_dir)], timeout=60)
            comment_on_issue(repo, issue_number, "📦 Repository cloned.", github_token)
        except subprocess.TimeoutExpired as e:
            comment_on_issue(repo, issue_number, f"⏱️ Clone timed out after 60s: {e}", github_token)
            return None
        except subprocess.CalledProcessError as e:
            comment_on_issue(repo, issue_number, f"❌ Clone failed: {e}", github_token)
            return None

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
                comment_on_issue(repo, issue_number, f"📌 Checked out commit `{agent.commit[:8]}` (from local repo)", github_token)
                checkout_success = True
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                print(f"⚠️ Local checkout failed: {e}")

        # If not successful, try fetching with timeout
        if not checkout_success:
            try:
                print(f"⚙️ Fetching from origin (timeout: 30s)...")
                run_command(["git", "fetch", "origin"], cwd=repo_dir, timeout=30)
                run_command(["git", "checkout", agent.commit], cwd=repo_dir, timeout=30)
                comment_on_issue(repo, issue_number, f"📌 Checked out commit `{agent.commit[:8]}`", github_token)
            except subprocess.TimeoutExpired as e:
                comment_on_issue(repo, issue_number, f"❌ Git fetch timed out after 30s. Cannot get commit `{agent.commit[:8]}`", github_token)
                print(f"❌ Git fetch timed out for {agent.commit[:8]}")
                return None
            except subprocess.CalledProcessError as e:
                comment_on_issue(repo, issue_number, f"❌ Git fetch/checkout failed for commit `{agent.commit[:8]}`", github_token)
                print(f"❌ Git fetch/checkout failed: {e}")
                return None

    # Detect and build based on project type
    print("=" * 60)
    print("🚀 [v4.0] BACKWARD-COMPATIBLE DOCKERFILE ARCHITECTURE")
    print("=" * 60)
    project_type, needs_pre_build = detect_project_type(repo_dir)
    print(f"📋 Project type detected: {project_type}, needs_pre_build: {needs_pre_build}")
    comment_on_issue(repo, issue_number, f"📋 Detected project type: **{project_type}**", github_token)

    if not build_project(repo_dir, project_type, needs_pre_build, github_token, issue_number):
        return None

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
        # Use --no-daemon to avoid gradle cache corruption issues
        subprocess.run(
            ["./gradlew", "runEvaluation", f"--args={port}", "--no-daemon"],
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


def stop_and_cleanup_container(agent_id: str, short_commit: str, github_token: str, issue_number: int):
    container_name = f"container-{agent_id}-{short_commit}"
    try:
        run_command(["podman", "stop", container_name])
        run_command(["podman", "rm", container_name])
        comment_on_issue("SimonLucas/planet-wars-rts-submissions", issue_number,
                         "✅ Evaluation complete. Container stopped and removed.", github_token)
    except subprocess.CalledProcessError as e:
        # Container might already be stopped/removed, or never started - that's ok
        comment_on_issue("SimonLucas/planet-wars-rts-submissions", issue_number,
                         f"⚠️ Container cleanup: {e} (This is usually harmless)", github_token)


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
        short_commit = agent.commit[:7]
        stop_and_cleanup_container(agent.id, short_commit, github_token, issue_number)
    except Exception as e:
        comment_on_issue("SimonLucas/planet-wars-rts-submissions", issue_number,
                         f"⚠️ Cleanup failed: {e}", github_token)

    # Step 7: Close issue
    close_issue("SimonLucas/planet-wars-rts-submissions", issue_number, github_token)

    return success
