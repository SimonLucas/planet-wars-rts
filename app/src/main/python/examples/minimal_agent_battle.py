#!/usr/bin/env python3
"""
Minimal example: Battle two agents.

The simplest possible script to clone, launch, and evaluate two agents.
Customize the agent details below and run.
"""

from pathlib import Path
from runner_utils.agent_entry import AgentEntry
from runner_utils.launch_agent import launch_agent
from league.run_pair_eval import run_remote_pair_evaluation
from runner_utils.shut_down_all_containers import stop_and_remove_container
import time


# =============================================================================
# CUSTOMIZE THESE AGENT DETAILS
# =============================================================================

AGENT_1 = AgentEntry(
    id="my-agent-v1",
    repo_url="https://github.com/SimonLucas/planet-wars-rts.git",
    commit="cc96b07"  # Optional: None for latest
)

AGENT_2 = AgentEntry(
    id="my-agent-v2",
    repo_url="https://github.com/SimonLucas/planet-wars-rts.git",
    commit="42766d5"  # Optional: None for latest
)

WORK_DIR = Path.home() / "planet-wars-demo"  # Where to clone repos
NUM_GAMES = 10  # How many games to play

# =============================================================================


def main():
    """Clone, launch, evaluate, and cleanup."""

    WORK_DIR.mkdir(exist_ok=True)

    print(f"\n🤖 Agent 1: {AGENT_1.id}")
    print(f"🤖 Agent 2: {AGENT_2.id}")
    print(f"🎮 Games: {NUM_GAMES}\n")

    try:
        # Launch both agents
        print("🚀 Launching agents (this may take a minute)...\n")
        launch_agent(AGENT_1, WORK_DIR)
        time.sleep(3)
        launch_agent(AGENT_2, WORK_DIR)
        time.sleep(5)

        # Run games
        print(f"\n🎮 Playing {NUM_GAMES} games...\n")
        output, avg1, avg2 = run_remote_pair_evaluation(
            port_a=AGENT_1.port,
            port_b=AGENT_2.port,
            games_per_pair=NUM_GAMES,
            timeout_ms=40
        )

        # Show results
        print(f"\n📊 Results:")
        print(f"   {AGENT_1.id}: {avg1:.1f}")
        print(f"   {AGENT_2.id}: {avg2:.1f}")
        print(f"\n🏆 Winner: {AGENT_1.id if avg1 > avg2 else AGENT_2.id if avg2 > avg1 else 'TIE'}\n")

    finally:
        # Cleanup
        print("🧹 Cleaning up containers...")
        for agent in [AGENT_1, AGENT_2]:
            try:
                stop_and_remove_container(f"container-{agent.id}")
            except:
                pass
        print("✨ Done!\n")


if __name__ == "__main__":
    main()
