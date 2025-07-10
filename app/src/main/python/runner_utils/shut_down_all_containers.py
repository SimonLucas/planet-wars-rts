import subprocess
import re
from typing import List, Optional
from runner_utils.agent_entry import AgentEntry
from runner_utils.utils import run_command


def stop_and_remove_container(container_name: str):
    try:
        run_command(["podman", "stop", container_name])
        run_command(["podman", "rm", container_name])
        print(f"🛑 Stopped and removed container: {container_name}")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Could not stop/remove container {container_name}: {e}")


def shutdown_by_agent_list(agent_list: List[AgentEntry]):
    print("🔻 Shutting down containers listed in agent list...")
    for agent in agent_list:
        stop_and_remove_container(f"container-{agent.id}")
    print("✅ Listed agents shut down.")


def shutdown_all_matching_containers(pattern: str = r'^container-'):
    print("🔻 Scanning for all matching containers to shut down...")
    try:
        result = subprocess.run(
            ["podman", "ps", "-a", "--format", "{{.Names}}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            text=True
        )
        all_containers = result.stdout.strip().splitlines()
        matching = [name for name in all_containers if re.match(pattern, name)]

        if not matching:
            print("⚠️ No matching containers found.")
            return

        for name in matching:
            stop_and_remove_container(name)

        print(f"✅ {len(matching)} container(s) shut down.")

    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to list containers: {e.stderr}")


# Optional command-line entry point
if __name__ == "__main__":
    from runner_utils.competition_entries import sample_entries

    print("🔧 Choose shutdown mode:")
    print("1. Only sample entries")
    print("2. All containers starting with 'container-'")

    choice = input("Enter 1 or 2: ").strip()
    if choice == "1":
        shutdown_by_agent_list(sample_entries)
    elif choice == "2":
        shutdown_all_matching_containers()
    else:
        print("❌ Invalid choice.")
