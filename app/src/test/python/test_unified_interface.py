"""
Comprehensive test suite for the unified agent interface.

Tests all components of the unified interface including observations,
adapters, and the unified game runner in both fully and partially observable modes.
"""

import unittest
from typing import Set

from core.game_state import GameParams, GameState, Player, Action
from core.game_state_factory import GameStateFactory
from core.observation import Observation, ObservationFactory
from core.game_state_reconstructor import (
    HiddenInfoSampler,
    DefaultHiddenInfoSampler,
    GameStateReconstructor
)
from agents.planet_wars_agent import PlanetWarsPlayer
from agents.random_agents import CarefulRandomAgent, PureRandomAgent
from agents.greedy_heuristic_agent import GreedyHeuristicAgent
from agents.fully_observable_agent_adapter import as_unified, FullyObservableAgentAdapter
from core.unified_game_runner import UnifiedGameRunner
from core.game_runner import GameRunner


class TestObservationFactory(unittest.TestCase):
    """Test observation creation and visibility rules."""

    def setUp(self):
        self.params = GameParams(num_planets=10)
        self.game_state = GameStateFactory(self.params).create_game()

    def test_fully_observable_has_no_nulls(self):
        """Test that fully observable observations have all information visible."""
        observation = ObservationFactory.create(
            self.game_state,
            {Player.Player1, Player.Player2, Player.Neutral}
        )

        for planet in observation.observed_planets:
            self.assertIsNotNone(
                planet.n_ships,
                f"Planet {planet.id} should have visible ships in fully observable mode"
            )
            if planet.transporter is not None:
                self.assertIsNotNone(
                    planet.transporter.n_ships,
                    f"Transporter on planet {planet.id} should have visible ships"
                )

    def test_partially_observable_has_nulls_for_opponents(self):
        """Test that partial observations hide opponent information."""
        observation = ObservationFactory.create(
            self.game_state,
            {Player.Player1}
        )

        player1_planets = [p for p in observation.observed_planets if p.owner == Player.Player1]
        opponent_planets = [p for p in observation.observed_planets if p.owner != Player.Player1]

        # Player1 planets should be fully visible
        for planet in player1_planets:
            self.assertIsNotNone(planet.n_ships, "Own planets should have visible ships")

        # Opponent/neutral planets should have hidden ship counts
        for planet in opponent_planets:
            self.assertIsNone(
                planet.n_ships,
                f"Opponent/neutral planet {planet.id} should have hidden ships"
            )

    def test_observation_contains_all_planets(self):
        """Test that observations include all planets."""
        observation = ObservationFactory.create(self.game_state, {Player.Player1})
        self.assertEqual(
            len(observation.observed_planets),
            len(self.game_state.planets),
            "Observation should include all planets"
        )

    def test_observation_game_tick_matches(self):
        """Test that observation game tick matches state."""
        observation = ObservationFactory.create(self.game_state, {Player.Player1})
        self.assertEqual(
            observation.game_tick,
            self.game_state.game_tick,
            "Observation game tick should match state"
        )


class TestGameStateReconstructor(unittest.TestCase):
    """Test game state reconstruction from observations."""

    def setUp(self):
        self.params = GameParams(num_planets=5)
        self.game_state = GameStateFactory(self.params).create_game()
        self.sampler = DefaultHiddenInfoSampler(self.params)
        self.reconstructor = GameStateReconstructor(self.sampler)

    def test_reconstruction_from_partial_observation(self):
        """Test reconstructing game state from partial observation."""
        observation = ObservationFactory.create(self.game_state, {Player.Player1})
        reconstructed = self.reconstructor.reconstruct(observation)

        self.assertEqual(
            len(reconstructed.planets),
            len(self.game_state.planets),
            "Reconstructed state should have all planets"
        )

        # All planets should have ship counts (no None values)
        for planet in reconstructed.planets:
            self.assertIsNotNone(planet.n_ships, "Reconstructed planets should have ship counts")

    def test_reconstruction_preserves_visible_information(self):
        """Test that reconstruction preserves visible (own) planet information."""
        observation = ObservationFactory.create(self.game_state, {Player.Player1})
        reconstructed = self.reconstructor.reconstruct(observation)

        # Find matching planets by ID
        for orig_planet in self.game_state.planets:
            if orig_planet.owner == Player.Player1:
                recon_planet = reconstructed.planets[orig_planet.id]
                self.assertEqual(
                    orig_planet.n_ships,
                    recon_planet.n_ships,
                    f"Own planet {orig_planet.id} ships should be preserved exactly"
                )

    def test_custom_sampler(self):
        """Test reconstruction with custom sampler."""
        class ConstantSampler:
            def sample_ships(self) -> float:
                return 10.0

            def sample_transporter_ships(self) -> float:
                return 5.0

        custom_sampler = ConstantSampler()
        reconstructor = GameStateReconstructor(custom_sampler)
        observation = ObservationFactory.create(self.game_state, {Player.Player1})
        reconstructed = reconstructor.reconstruct(observation)

        # Opponent planets should have the constant sampled value
        for planet in reconstructed.planets:
            if planet.owner != Player.Player1:
                self.assertEqual(
                    planet.n_ships,
                    10.0,
                    "Custom sampler should be used for hidden information"
                )


class TestFullyObservableAgentAdapter(unittest.TestCase):
    """Test adapter for wrapping fully observable agents."""

    def setUp(self):
        self.params = GameParams(num_planets=10)
        self.game_state = GameStateFactory(self.params).create_game()

    def test_adapter_wraps_agent_correctly(self):
        """Test that adapter correctly wraps an agent."""
        greedy_agent = GreedyHeuristicAgent()
        unified_agent = as_unified(greedy_agent)

        self.assertIsNotNone(unified_agent)
        self.assertEqual(
            unified_agent.get_agent_type(),
            "Greedy Heuristic Agent in Python"
        )

    def test_adapter_prepare_to_play_as(self):
        """Test that adapter delegates prepare_to_play_as correctly."""
        careful_agent = CarefulRandomAgent()
        unified_agent = as_unified(careful_agent)

        agent_type = unified_agent.prepare_to_play_as(Player.Player1, self.params, "TestOpponent")
        self.assertEqual(agent_type, "Careful Random Agent")

    def test_adapter_works_with_fully_observable(self):
        """Test adapter with fully observable observations."""
        careful_agent = CarefulRandomAgent()
        unified_agent = as_unified(careful_agent)
        unified_agent.prepare_to_play_as(Player.Player1, self.params)

        observation = ObservationFactory.create(
            self.game_state,
            {Player.Player1, Player.Player2, Player.Neutral}
        )

        action = unified_agent.get_action(observation)
        self.assertIsNotNone(action)
        self.assertIsInstance(action, Action)

    def test_adapter_works_with_partially_observable(self):
        """Test adapter with partially observable observations."""
        careful_agent = CarefulRandomAgent()
        unified_agent = as_unified(careful_agent)
        unified_agent.prepare_to_play_as(Player.Player1, self.params)

        observation = ObservationFactory.create(self.game_state, {Player.Player1})

        action = unified_agent.get_action(observation)
        self.assertIsNotNone(action)
        self.assertIsInstance(action, Action)

    def test_adapter_optimization_detects_fully_observable(self):
        """Test that adapter correctly detects fully observable mode."""
        agent = as_unified(CarefulRandomAgent())
        agent.prepare_to_play_as(Player.Player1, self.params)

        # Fully observable
        full_obs = ObservationFactory.create(
            self.game_state,
            {Player.Player1, Player.Player2, Player.Neutral}
        )
        all_visible = all(p.n_ships is not None for p in full_obs.observed_planets)
        self.assertTrue(all_visible, "Fully observable should have all ships visible")

    def test_adapter_with_custom_sampler(self):
        """Test adapter with custom sampler."""
        class CustomSampler:
            def sample_ships(self) -> float:
                return 15.0

            def sample_transporter_ships(self) -> float:
                return 7.5

        agent = CarefulRandomAgent()
        unified_agent = FullyObservableAgentAdapter(agent, CustomSampler())
        unified_agent.prepare_to_play_as(Player.Player1, self.params)

        observation = ObservationFactory.create(self.game_state, {Player.Player1})
        action = unified_agent.get_action(observation)
        self.assertIsNotNone(action)


class TestUnifiedGameRunner(unittest.TestCase):
    """Test unified game runner in both modes."""

    def setUp(self):
        self.params = GameParams(num_planets=10, max_ticks=100)

    def test_runner_in_fully_observable_mode(self):
        """Test runner executes games in fully observable mode."""
        agent1 = as_unified(CarefulRandomAgent())
        agent2 = as_unified(PureRandomAgent())

        runner = UnifiedGameRunner(agent1, agent2, self.params, partial_observability=False)
        result = runner.run_game()

        self.assertIsNotNone(result)
        self.assertTrue(result.is_terminal())

    def test_runner_in_partially_observable_mode(self):
        """Test runner executes games in partially observable mode."""
        agent1 = as_unified(CarefulRandomAgent())
        agent2 = as_unified(PureRandomAgent())

        runner = UnifiedGameRunner(agent1, agent2, self.params, partial_observability=True)
        result = runner.run_game()

        self.assertIsNotNone(result)
        self.assertTrue(result.is_terminal())

    def test_runner_runs_multiple_games(self):
        """Test runner can execute multiple games."""
        agent1 = as_unified(CarefulRandomAgent())
        agent2 = as_unified(PureRandomAgent())

        runner = UnifiedGameRunner(agent1, agent2, self.params, partial_observability=False)
        scores = runner.run_games(10)

        self.assertIsNotNone(scores)
        self.assertEqual(len(scores), 3)  # Player1, Player2, Neutral
        self.assertEqual(sum(scores.values()), 10, "Total games should be 10")

    def test_process_game_over_is_called(self):
        """Test that process_game_over is called on agents."""
        game_over_called = []

        class TestAgent(PlanetWarsPlayer):
            def get_action(self, game_state: GameState) -> Action:
                return Action.do_nothing()

            def get_agent_type(self) -> str:
                return "Test Agent"

            def process_game_over(self, final_state: GameState) -> None:
                game_over_called.append(True)

        agent = as_unified(TestAgent())
        runner = UnifiedGameRunner(
            agent,
            as_unified(PureRandomAgent()),
            GameParams(num_planets=5, max_ticks=10),
            partial_observability=False
        )

        runner.run_game()
        self.assertTrue(len(game_over_called) > 0, "process_game_over should be called")


class TestBackwardCompatibility(unittest.TestCase):
    """Test that existing code still works unchanged."""

    def setUp(self):
        self.params = GameParams(num_planets=10, max_ticks=100)

    def test_existing_game_runner_still_works(self):
        """Verify that existing GameRunner is not broken."""
        agent1 = CarefulRandomAgent()
        agent2 = PureRandomAgent()

        runner = GameRunner(agent1, agent2, self.params)
        result = runner.run_game()

        self.assertIsNotNone(result)
        self.assertTrue(result.is_terminal())

    def test_existing_agents_still_work(self):
        """Verify that existing agents work without modification."""
        agent = CarefulRandomAgent()
        agent.prepare_to_play_as(Player.Player1, self.params)

        game_state = GameStateFactory(self.params).create_game()
        action = agent.get_action(game_state)

        self.assertIsNotNone(action)
        self.assertIsInstance(action, Action)


if __name__ == "__main__":
    unittest.main()
