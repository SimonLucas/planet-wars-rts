"""
Adapter for wrapping fully observable agents to work with the unified interface.

This module provides an adapter that allows existing PlanetWarsAgent implementations
to work seamlessly with the unified Observation-based interface, enabling them to
participate in both fully and partially observable games.
"""

from typing import Optional

from agents.planet_wars_agent import PlanetWarsAgent, UnifiedPlanetWarsAgent
from core.game_state import GameState, GameParams, Player, Action, Planet, Transporter
from core.observation import Observation
from core.game_state_reconstructor import HiddenInfoSampler, DefaultHiddenInfoSampler


class FullyObservableAgentAdapter(UnifiedPlanetWarsAgent):
    """
    Smart adapter that wraps a PlanetWarsAgent to work with the unified Observation interface.

    This adapter allows existing fully observable agents to participate in both fully
    and partially observable games without modification. The adapter intelligently
    detects whether an observation contains hidden information and optimizes accordingly:

    - In fully observable games: Direct conversion without sampling (zero overhead)
    - In partially observable games: Uses HiddenInfoSampler to reconstruct missing information

    Args:
        wrapped_agent: The existing PlanetWarsAgent to adapt
        sampler: Optional custom sampler for hidden information. If None, uses DefaultHiddenInfoSampler

    Example:
        >>> greedy_agent = GreedyHeuristicAgent()
        >>> unified_agent = FullyObservableAgentAdapter(greedy_agent)
        >>> # Or using extension function:
        >>> unified_agent2 = greedy_agent.as_unified()
    """

    def __init__(
        self,
        wrapped_agent: PlanetWarsAgent,
        sampler: Optional[HiddenInfoSampler] = None
    ):
        self.wrapped_agent = wrapped_agent
        self.sampler = sampler
        self.params: GameParams = GameParams()
        self.reconstructor: Optional['GameStateReconstructor'] = None

    def get_action(self, observation: Observation) -> Action:
        """
        Convert observation to GameState and delegate to wrapped agent.

        Automatically detects if observation is fully observable and optimizes conversion.

        Args:
            observation: Game observation (may contain hidden information)

        Returns:
            Action from the wrapped agent
        """
        if self._is_fully_observable(observation):
            # No hidden information - directly convert without sampling (zero overhead)
            game_state = self._observation_to_game_state(observation)
        else:
            # Has hidden information - use reconstructor with sampling
            if self.reconstructor is None:
                # Lazy initialize reconstructor
                from core.game_state_reconstructor import GameStateReconstructor
                effective_sampler = self.sampler or DefaultHiddenInfoSampler(self.params)
                self.reconstructor = GameStateReconstructor(effective_sampler)

            game_state = self.reconstructor.reconstruct(observation)

        return self.wrapped_agent.get_action(game_state)

    def get_agent_type(self) -> str:
        """Get agent type from wrapped agent."""
        return self.wrapped_agent.get_agent_type()

    def prepare_to_play_as(
        self,
        player: Player,
        params: GameParams,
        opponent: Optional[str] = None
    ) -> str:
        """
        Prepare both adapter and wrapped agent to play.

        Args:
            player: Which player this agent will be
            params: Game parameters
            opponent: Optional opponent identifier

        Returns:
            Agent type string
        """
        self.params = params

        # Initialize reconstructor with effective sampler if needed
        if self.sampler is None:
            from core.game_state_reconstructor import GameStateReconstructor
            effective_sampler = DefaultHiddenInfoSampler(params)
            self.reconstructor = GameStateReconstructor(effective_sampler)
        else:
            from core.game_state_reconstructor import GameStateReconstructor
            self.reconstructor = GameStateReconstructor(self.sampler)

        # Forward to wrapped agent
        return self.wrapped_agent.prepare_to_play_as(player, params, opponent)

    def process_game_over(self, final_state: GameState) -> None:
        """
        Forward game over notification to wrapped agent.

        Args:
            final_state: Complete final game state
        """
        self.wrapped_agent.process_game_over(final_state)

    def _is_fully_observable(self, observation: Observation) -> bool:
        """
        Check if observation contains any hidden information (None values).

        Returns:
            True if all information is visible (fully observable)
        """
        for planet in observation.observed_planets:
            # Check if planet ships are hidden
            if planet.n_ships is None:
                return False

            # Check if transporter ships are hidden
            if planet.transporter is not None:
                if planet.transporter.n_ships is None:
                    return False

        return True

    def _observation_to_game_state(self, observation: Observation) -> GameState:
        """
        Convert fully observable observation directly to GameState without sampling.

        This method should only be called when _is_fully_observable() returns True.

        Args:
            observation: Fully observable observation

        Returns:
            Complete GameState
        """
        planets = []

        for observed in observation.observed_planets:
            # Safe to use ! because we checked _is_fully_observable
            transporter = None
            if observed.transporter is not None:
                trans_obs = observed.transporter
                transporter = Transporter(
                    s=trans_obs.s,
                    v=trans_obs.v,
                    owner=trans_obs.owner,
                    source_index=trans_obs.source_index,
                    destination_index=trans_obs.destination_index,
                    n_ships=trans_obs.n_ships  # type: ignore  # Checked by is_fully_observable
                )

            planets.append(Planet(
                owner=observed.owner,
                n_ships=observed.n_ships,  # type: ignore  # Checked by is_fully_observable
                position=observed.position,
                growth_rate=observed.growth_rate,
                radius=observed.radius,
                transporter=transporter,
                id=observed.id
            ))

        return GameState(planets=planets, game_tick=observation.game_tick)


# Extension function for easy adapter creation
def as_unified(
    agent: PlanetWarsAgent,
    sampler: Optional[HiddenInfoSampler] = None
) -> UnifiedPlanetWarsAgent:
    """
    Extension function to easily wrap a PlanetWarsAgent for use with the unified interface.

    This allows existing fully observable agents to work in both fully and partially
    observable games without modification.

    Args:
        agent: The agent to wrap
        sampler: Optional custom sampler for hidden information reconstruction

    Returns:
        A UnifiedPlanetWarsAgent that wraps the original agent

    Example:
        >>> from agents.greedy_heuristic_agent import GreedyHeuristicAgent
        >>> from agents.fully_observable_agent_adapter import as_unified
        >>>
        >>> greedy_agent = GreedyHeuristicAgent()
        >>> unified_agent = as_unified(greedy_agent)
    """
    return FullyObservableAgentAdapter(agent, sampler)


# Example usage
if __name__ == "__main__":
    from agents.random_agents import CarefulRandomAgent
    from core.game_state_factory import GameStateFactory
    from core.observation import ObservationFactory

    # Create a fully observable agent
    random_agent = CarefulRandomAgent()

    # Wrap it for unified interface
    unified_agent = as_unified(random_agent)

    # Prepare to play
    params = GameParams(num_planets=10)
    unified_agent.prepare_to_play_as(Player.Player1, params)

    # Create a game state
    game_state = GameStateFactory(params).create_game()

    # Test with fully observable observation
    full_obs = ObservationFactory.create(
        game_state,
        {Player.Player1, Player.Player2, Player.Neutral}
    )
    action1 = unified_agent.get_action(full_obs)
    print(f"Action from fully observable: {action1}")

    # Test with partially observable observation
    partial_obs = ObservationFactory.create(game_state, {Player.Player1})
    action2 = unified_agent.get_action(partial_obs)
    print(f"Action from partially observable: {action2}")

    print("\nAdapter successfully works in both modes!")
