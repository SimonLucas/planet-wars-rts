from pathlib import Path
from runner_utils.competition_entries import sample_entries
from runner_utils.launch_agent import launch_agent

if __name__ == "__main__":

    base_dir = Path("/tmp/simonl-planetwars-run")

    # just launch the final sample agent

    # sample_entries = sample_entries
    final_entry = sample_entries[-1]
    # sample_entries = [final_entry]

    for agent in sample_entries:
        print(f"Launching agent: {agent.id}")
        launch_agent(agent, base_dir)
        print(f"Agent {agent.id} launched successfully.")

