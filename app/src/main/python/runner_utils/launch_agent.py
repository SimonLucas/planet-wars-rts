import subprocess
from pathlib import Path
from typing import Optional
from runner_utils.clone_utils import robust_clone_and_build


# def run_command(cmd: list[str], cwd: Optional[Path] = None):
#     print(f"Running: {' '.join(cmd)} (in {cwd or Path.cwd()})")
#     subprocess.run(cmd, check=True, cwd=cwd)


from pathlib import Path
from runner_utils.agent_entry import AgentEntry
from runner_utils.utils import run_command, find_free_port
from util.scan_closed_issues_for_results import load_github_token

import subprocess


def launch_agent(agent: AgentEntry, base_dir: Path):
    from util.scan_closed_issues_for_results import load_github_token
    github_token = load_github_token()

    repo_dir = robust_clone_and_build(agent, base_dir, github_token)
    if repo_dir is None:
        raise RuntimeError(f"Failed to prepare {agent.id}")

    port = agent.port or find_free_port()
    agent.port = port

    image_name = f"game-server-{agent.id}"
    container_name = f"container-{agent.id}"

    run_command(["podman", "build", "-t", image_name, "."], cwd=repo_dir)

    try:
        run_command(["podman", "rm", "-f", container_name])
    except subprocess.CalledProcessError:
        pass

    run_command([
        "podman", "run", "-d",
        "-p", f"{port}:8080",
        "--name", container_name,
        image_name
    ])

    print(f"🚀 Agent {agent.id} is running at http://localhost:{port}")
