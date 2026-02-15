"""
Unified game runner that supports both fully and partially observable game modes.

This module provides a single game runner interface that can execute games in either
fully or partially observable mode with the same agents.
"""

from typing import Dict
from core.forward_model import ForwardModel
from core.game_state import GameParams, GameState, Player
from core.game_state_factory import GameStateFactory
from core.observation import ObservationFactory
from agents.planet_wars_agent import UnifiedPlanetWarsAgent


class UnifiedGameRunner:
    """
    Game runner that works with the unified agent interface, supporting both fully
    and partially observable game modes with a single interface.

    This runner can execute games in either:
    - Fully observable mode: Agents receive observations with complete information (no None values)
    - Partially observable mode: Agents receive observations with hidden information (None for opponent data)

    Args:
        agent1: The first unified agent
        agent2: The second unified agent
        game_params: Game parameters
        partial_observability: If True, runs in partially observable mode; if False, fully observable mode

    Example:
        >>> from agents.fully_observable_agent_adapter import as_unified
        >>> from agents.random_agents import CarefulRandomAgent
        >>> from agents.greedy_heuristic_agent import GreedyHeuristicAgent
        >>>
        >>> # Wrap existing agents
        >>> agent1 = as_unified(CarefulRandomAgent())
        >>> agent2 = as_unified(GreedyHeuristicAgent())
        >>>
        >>> # Run in fully observable mode
        >>> runner1 = UnifiedGameRunner(agent1, agent2, GameParams(), partial_observability=False)
        >>> runner1.run_game()
        >>>
        >>> # Run same agents in partially observable mode!
        >>> runner2 = UnifiedGameRunner(agent1, agent2, GameParams(), partial_observability=True)
        >>> runner2.run_game()
    """

    def __init__(
        self,
        agent1: UnifiedPlanetWarsAgent,
        agent2: UnifiedPlanetWarsAgent,
        game_params: GameParams,
        partial_observability: bool = False
    ):
        self.agent1 = agent1
        self.agent2 = agent2
        self.game_params = game_params
        self.partial_observability = partial_observability
        self.game_state: GameState = GameStateFactory(game_params).create_game()
        self.forward_model: ForwardModel = ForwardModel(
            self.game_state.model_copy(deep=True),
            game_params
        )
        self.new_game()

    def run_game(self) -> ForwardModel:
        """
        Run a complete game from start to finish.

        Returns:
            ForwardModel containing the final game state and statistics
        """
        self.new_game()
        while not self.forward_model.is_terminal():
            game_state = self.forward_model.state

            # Create observations based on observability mode
            if self.partial_observability:
                # Partially observable: each player sees only their own information
                p1_observation = ObservationFactory.create(game_state, {Player.Player1})
                p2_observation = ObservationFactory.create(game_state, {Player.Player2})
            else:
                # Fully observable: both players see everything (including neutral planets)
                p1_observation = ObservationFactory.create(
                    game_state,
                    {Player.Player1, Player.Player2, Player.Neutral}
                )
                p2_observation = ObservationFactory.create(
                    game_state,
                    {Player.Player1, Player.Player2, Player.Neutral}
                )

            actions = {
                Player.Player1: self.agent1.get_action(p1_observation),
                Player.Player2: self.agent2.get_action(p2_observation),
            }
            self.forward_model.step(actions)

        # Notify agents that the game is over
        self.agent1.process_game_over(self.forward_model.state)
        self.agent2.process_game_over(self.forward_model.state)

        return self.forward_model

    def new_game(self) -> None:
        """Initialize or reset the game."""
        if self.game_params.new_map_each_run:
            self.game_state = GameStateFactory(self.game_params).create_game()

        self.forward_model = ForwardModel(
            self.game_state.model_copy(deep=True),
            self.game_params
        )
        self.agent1.prepare_to_play_as(Player.Player1, self.game_params)
        self.agent2.prepare_to_play_as(Player.Player2, self.game_params)

    def step_game(self) -> ForwardModel:
        """
        Step the game forward by one tick.

        Returns:
            ForwardModel with updated state
        """
        if self.forward_model.is_terminal():
            return self.forward_model

        game_state = self.forward_model.state

        # Create observations based on observability mode
        if self.partial_observability:
            p1_observation = ObservationFactory.create(game_state, {Player.Player1})
            p2_observation = ObservationFactory.create(game_state, {Player.Player2})
        else:
            p1_observation = ObservationFactory.create(
                game_state,
                {Player.Player1, Player.Player2, Player.Neutral}
            )
            p2_observation = ObservationFactory.create(
                game_state,
                {Player.Player1, Player.Player2, Player.Neutral}
            )

        actions = {
            Player.Player1: self.agent1.get_action(p1_observation),
            Player.Player2: self.agent2.get_action(p2_observation),
        }
        self.forward_model.step(actions)
        return self.forward_model

    def run_games(self, n_games: int) -> Dict[Player, int]:
        """
        Run multiple games and return the results.

        Args:
            n_games: Number of games to run

        Returns:
            Dictionary mapping each player to their win count
        """
        scores = {Player.Player1: 0, Player.Player2: 0, Player.Neutral: 0}
        for _ in range(n_games):
            final_model = self.run_game()
            winner = final_model.get_leader()
            scores[winner] += 1
        return scores


# Example usage / demonstration
if __name__ == "__main__":
    import time
    from agents.random_agents import PureRandomAgent, CarefulRandomAgent
    from agents.fully_observable_agent_adapter import as_unified

    game_params = GameParams(num_planets=20)
    n_games = 100  # Number of games for performance test

    # Wrap existing agents using the unified interface
    agent1 = as_unified(PureRandomAgent())
    agent2 = as_unified(CarefulRandomAgent())

    print("=== Testing Fully Observable Mode ===")
    fully_observable_runner = UnifiedGameRunner(
        agent1, agent2, game_params, partial_observability=False
    )
    fully_observable_result = fully_observable_runner.run_game()
    print("Game over!")
    print(fully_observable_result.status_string())

    print("\n=== Testing Partially Observable Mode ===")
    partially_observable_runner = UnifiedGameRunner(
        agent1, agent2, game_params, partial_observability=True
    )
    partially_observable_result = partially_observable_runner.run_game()
    print("Game over!")
    print(partially_observable_result.status_string())



    print(f"\n=== Running Performance Test ({n_games} games each) ===")

    # Test fully observable
    t1 = time.time()
    fully_observable_scores = fully_observable_runner.run_games(n_games)
    dt1 = time.time() - t1
    print(f"\nFully Observable Results ({n_games} games):")
    print(fully_observable_scores)
    print(f"Time per game: {dt1 / n_games * 1000:.3f} ms")

    # Test partially observable
    t2 = time.time()
    partially_observable_scores = partially_observable_runner.run_games(n_games)
    dt2 = time.time() - t2
    print(f"\nPartially Observable Results ({n_games} games):")
    print(partially_observable_scores)
    print(f"Time per game: {dt2 / n_games * 1000:.3f} ms")

    print(f"\nSuccessful actions: {ForwardModel.n_actions}")
    print(f"Failed actions: {ForwardModel.n_failed_actions}")
