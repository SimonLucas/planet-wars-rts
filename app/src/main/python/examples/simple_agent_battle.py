#!/usr/bin/env python3
"""
Simple example: Clone, launch, and evaluate two agents against each other.

This script demonstrates the complete workflow:
1. Clone two agent repositories from GitHub
2. Build and launch them in Podman containers
3. Run games between them and show results
4. Clean up containers when done

Usage:
    python3 -m examples.simple_agent_battle

Requirements:
    - Podman installed and running
    - GitHub token in ~/.github_submission_token (for cloning private repos)
    - PYTHONPATH set to app/src/main/python
"""

from pathlib import Path
from runner_utils.agent_entry import AgentEntry
from runner_utils.launch_agent import launch_agent
from league.run_pair_eval import run_remote_pair_evaluation
from runner_utils.shut_down_all_containers import stop_and_remove_container
import time


def main():
    """
    Run a simple battle between two agents.
    """

    # ============================================================
    # STEP 1: Define the two agents you want to battle
    # ============================================================

    print("=" * 70)
    print("SIMPLE AGENT BATTLE EXAMPLE")
    print("=" * 70)

    # Agent 1: Replace with your first agent's details
    agent1 = AgentEntry(
        id="agent-alice",
        repo_url="https://github.com/SimonLucas/planet-wars-rts.git",
        commit="cc96b07"  # Optional: specify a commit, or leave None for latest
    )

    # Agent 2: Replace with your second agent's details
    agent2 = AgentEntry(
        id="agent-bob",
        repo_url="https://github.com/SimonLucas/planet-wars-rts.git",
        commit="42766d5"  # Optional: specify a commit, or leave None for latest
    )

    # Where to clone repositories (change if needed)
    base_dir = Path.home() / "planet-wars-demo"
    base_dir.mkdir(exist_ok=True)

    print(f"\n📁 Working directory: {base_dir}")
    print(f"\n🤖 Agent 1: {agent1.id}")
    print(f"   Repository: {agent1.repo_url}")
    print(f"   Commit: {agent1.commit or 'latest'}")
    print(f"\n🤖 Agent 2: {agent2.id}")
    print(f"   Repository: {agent2.repo_url}")
    print(f"   Commit: {agent2.commit or 'latest'}")

    # ============================================================
    # STEP 2: Launch both agents in Podman containers
    # ============================================================

    print("\n" + "=" * 70)
    print("LAUNCHING AGENTS")
    print("=" * 70)

    try:
        print(f"\n🚀 Launching {agent1.id}...")
        print("   (This will: clone repo, build project, create container, start server)")
        launch_agent(agent1, base_dir)
        port1 = agent1.port
        print(f"   ✅ Running on port {port1}")

        time.sleep(3)  # Brief delay between launches

        print(f"\n🚀 Launching {agent2.id}...")
        print("   (This will: clone repo, build project, create container, start server)")
        launch_agent(agent2, base_dir)
        port2 = agent2.port
        print(f"   ✅ Running on port {port2}")

        # Give servers time to fully start
        print("\n⏳ Waiting for servers to be ready...")
        time.sleep(5)

        # ============================================================
        # STEP 3: Run games between the agents
        # ============================================================

        print("\n" + "=" * 70)
        print("RUNNING GAMES")
        print("=" * 70)

        n_games = 10  # Number of games to play
        timeout_ms = 40  # Timeout per agent RPC call

        print(f"\n🎮 Playing {n_games} games between agents...")
        print(f"   Agent 1 port: {port1}")
        print(f"   Agent 2 port: {port2}")
        print(f"   Timeout per call: {timeout_ms}ms")
        print("\n   This will take a few moments...\n")

        # Run the evaluation (calls Kotlin via Gradle)
        output, avg_agent1, avg_agent2 = run_remote_pair_evaluation(
            port_a=port1,
            port_b=port2,
            games_per_pair=n_games,
            timeout_ms=timeout_ms
        )

        # ============================================================
        # STEP 4: Display results
        # ============================================================

        print("\n" + "=" * 70)
        print("RESULTS")
        print("=" * 70)

        print(f"\n📊 Average scores over {n_games} games:")
        print(f"   {agent1.id}: {avg_agent1:.1f}")
        print(f"   {agent2.id}: {avg_agent2:.1f}")

        if avg_agent1 > avg_agent2:
            winner = agent1.id
            margin = avg_agent1 - avg_agent2
        elif avg_agent2 > avg_agent1:
            winner = agent2.id
            margin = avg_agent2 - avg_agent1
        else:
            winner = "TIE"
            margin = 0

        print(f"\n🏆 Winner: {winner}")
        if margin > 0:
            print(f"   Margin: {margin:.1f} points")

        # Optionally show full output (can be verbose)
        show_full_output = False
        if show_full_output:
            print("\n" + "=" * 70)
            print("FULL GRADLE OUTPUT")
            print("=" * 70)
            print(output)

    finally:
        # ============================================================
        # STEP 5: Cleanup - stop and remove containers
        # ============================================================

        print("\n" + "=" * 70)
        print("CLEANUP")
        print("=" * 70)

        print(f"\n🧹 Stopping and removing containers...")

        try:
            stop_and_remove_container(f"container-{agent1.id}")
            print(f"   ✅ Removed container-{agent1.id}")
        except Exception as e:
            print(f"   ⚠️  Could not remove container-{agent1.id}: {e}")

        try:
            stop_and_remove_container(f"container-{agent2.id}")
            print(f"   ✅ Removed container-{agent2.id}")
        except Exception as e:
            print(f"   ⚠️  Could not remove container-{agent2.id}: {e}")

        print("\n✨ Done!")
        print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
