from pathlib import Path
from runner_utils.competition_entries import sample_entries
from runner_utils.launch_agent import launch_agent
import time

if __name__ == "__main__":

    # base_dir = Path("/tmp/gecco-planetwars")

    base_dir = Path.home() / "gecco-runs"  # Or wherever you'd like

    # just launch the final sample agent

    # sample_entries = sample_entries
    # final_entry = sample_entries[-1]
    # sample_entries = [final_entry]

    for agent in sample_entries:
        print(f"Launching agent: {agent.id}")
        launch_agent(agent, base_dir)
        print(f"Agent {agent.id} launched successfully.")
        time.sleep(2)  # delay to reduce chance of GitHub TLS failures

