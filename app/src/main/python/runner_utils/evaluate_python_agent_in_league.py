import subprocess
import sys
import time
from pathlib import Path
from typing import Type, Tuple

import multiprocessing
import re
from pathlib import Path
from agents.greedy_heuristic_agent import GreedyHeuristicAgent
from client_server.game_agent_server import GameServerAgent  # Adjust to actual import path


def extract_avg_win_rate(markdown: str) -> float:
    match = re.search(r"AVG=([0-9.]+)", markdown)
    if match:
        return float(match.group(1))
    else:
        raise ValueError("Average win rate not found in markdown.")


def find_project_root(start: Path = Path(__file__)) -> Path:
    for parent in start.resolve().parents:
        if (parent / "gradlew").is_file():
            return parent
    raise FileNotFoundError("Could not find 'gradlew' in any parent directory.")


def run_agent_server(port: int):
    import asyncio
    agent_server = GameServerAgent(port=port)
    asyncio.run(agent_server.start())


def evaluate_python_agent(agent_class: Type, port: int = 49875) -> Tuple[str, float]:
    # Launch the Python agent server in a separate process, return the league markdown and average win rate
    process = multiprocessing.Process(target=run_agent_server, args=(port,), daemon=True)
    process.start()

    # Give the server a moment to boot
    time.sleep(2)

    try:

        cwd = find_project_root()

        # Run Kotlin evaluation
        print("⚙️ Running evaluation via Gradle...")
        result = subprocess.run(
            ["./gradlew", "runEvaluation", f"--args={port}"],
            capture_output=True,
            text=True,
            cwd=cwd,
        )

        if result.returncode != 0:
            raise RuntimeError(f"❌ Evaluation failed:\n{result.stderr}")

        print("✅ Evaluation complete.")
        print(result.stdout)

        return result.stdout, extract_avg_win_rate(result.stdout)

    finally:
        # Terminate agent server process
        process.terminate()
        process.join(timeout=2)
        print("🛑 Python agent server stopped.")


if __name__ == "__main__":
    # time how long it takes to run the evaluation
    start_time = time.time()
    from agents.greedy_heuristic_agent import GreedyHeuristicAgent

    markdown, average = evaluate_python_agent(GreedyHeuristicAgent, port=49875)
    print("### Evaluation Results")
    print(markdown)
    print(f"Average win rate: {average:.2f}")
    end_time = time.time()
    print(f"Total evaluation time: {end_time - start_time:.2f} seconds")

    # Save the results to a markdown file if needed
    # with open("results/sample/evaluation_output.md", "w") as f:
    #     f.write(markdown)
