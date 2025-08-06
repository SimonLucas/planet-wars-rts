
"""
This is provided as an example of how to run quick evaluations for
your Python agents against a set of fixed Python agents as opponents.

Hint: as you develop better agents, update the `baseline_agents` list
to provide a more challenging set of opponents - otherwise you'r agent
may win 100% of games against these weak baselines, making it hard
to assess any further improvements.

"""

from typing import List, Dict, Tuple
from core.game_state import GameParams, Player
from core.forward_model import ForwardModel
from core.game_runner import GameRunner
from agents.random_agents import PureRandomAgent, CarefulRandomAgent  # adjust imports


def fast_agent_eval(
    test_agent,
    game_params: GameParams = GameParams(num_planets=10),
    baseline_agents: List = None,
    n_games: int = 100
) -> float:
    if baseline_agents is None:
        baseline_agents = [PureRandomAgent(), CarefulRandomAgent()]

    total_wins = 0
    total_games = 0

    for i, baseline in enumerate(baseline_agents):
        print(f"\nRunning test against baseline #{i + 1}: {baseline.__class__.__name__}")
        runner = GameRunner(test_agent, baseline, game_params)
        scores = runner.run_games(n_games)
        print(f"Scores: {scores}")
        print(f"Successful actions: {ForwardModel.n_actions}")
        print(f"Failed actions: {ForwardModel.n_failed_actions}")

        wins = scores.get(Player.Player1, 0)
        average = wins / n_games
        print(f"\nAverage win rate: {average:.3f}")

        total_wins += wins
        total_games += n_games

    average_win_rate = total_wins / total_games if total_games > 0 else 0.0
    return average_win_rate

if __name__ == "__main__":
    # provide sample usage of the fast_agent_eval function
    from agents.greedy_heuristic_agent import GreedyHeuristicAgent

    test_agent = GreedyHeuristicAgent()  # replace with your actual agent
    # time how long it takes to run the evaluation
    import time
    start_time = time.time()

    win_rate = fast_agent_eval(test_agent, n_games=10)
    print(f"\nFinal average win rate: {win_rate:.3f}")
    end_time = time.time()
    print(f"Total evaluation time: {end_time - start_time:.2f} seconds")
