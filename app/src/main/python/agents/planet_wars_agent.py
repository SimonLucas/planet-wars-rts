from abc import ABC, abstractmethod
from typing import Optional

from core.game_state import GameParams, GameState, Player, Action


DEFAULT_OPPONENT = "Anon"


# === Fully observable agent interface ===
class PlanetWarsAgent(ABC):

    @abstractmethod
    def get_action(self, game_state: GameState) -> Action:
        pass

    @abstractmethod
    def get_agent_type(self) -> str:
        pass

    def prepare_to_play_as(
        self,
        player: Player,
        params: GameParams,
        opponent: Optional[str] = DEFAULT_OPPONENT
    ) -> str:
        return self.get_agent_type()

    def process_game_over(self, final_state: GameState) -> None:
        pass


# === Fully observable abstract base class ===
class PlanetWarsPlayer(PlanetWarsAgent):
    def __init__(self):
        self.player: Player = Player.Neutral
        self.params: GameParams = GameParams()

    def prepare_to_play_as(
        self,
        player: Player,
        params: GameParams,
        opponent: Optional[str] = DEFAULT_OPPONENT
    ) -> str:
        self.player = player
        self.params = params
        return self.get_agent_type()


# === Unified agent interface ===
class UnifiedPlanetWarsAgent(ABC):
    """
    Unified interface that works with both fully and partially observable games.

    Agents receive Observations instead of GameStates. In fully observable mode,
    observations contain complete information (no None values). In partially
    observable mode, observations contain None for hidden information.

    This interface allows a single agent implementation to participate in both
    fully and partially observable games without modification.
    """

    @abstractmethod
    def get_action(self, observation: 'Observation') -> Action:
        """
        Get action from observation (may contain hidden information).

        Args:
            observation: Game observation from the agent's perspective

        Returns:
            Action to take
        """
        pass

    @abstractmethod
    def get_agent_type(self) -> str:
        """
        Get a string identifier for this agent type.

        Returns:
            Agent type name
        """
        pass

    def prepare_to_play_as(
        self,
        player: Player,
        params: GameParams,
        opponent: Optional[str] = DEFAULT_OPPONENT
    ) -> str:
        """
        Prepare agent to play as a specific player.

        Args:
            player: Which player this agent will be
            params: Game parameters
            opponent: Optional opponent identifier

        Returns:
            Agent type string
        """
        return self.get_agent_type()

    def process_game_over(self, final_state: GameState) -> None:
        """
        Process the final game state (always fully observable).

        Args:
            final_state: Complete final game state
        """
        pass


# === Unified abstract base class ===
class UnifiedPlanetWarsPlayer(UnifiedPlanetWarsAgent):
    """
    Abstract base class for unified agents with common functionality.

    Provides player/params management and helper methods for working with observations.
    """

    def __init__(self):
        self.player: Player = Player.Neutral
        self.params: GameParams = GameParams()

    def prepare_to_play_as(
        self,
        player: Player,
        params: GameParams,
        opponent: Optional[str] = DEFAULT_OPPONENT
    ) -> str:
        self.player = player
        self.params = params
        return self.get_agent_type()

    def to_game_state(
        self,
        observation: 'Observation',
        sampler: Optional['HiddenInfoSampler'] = None
    ) -> GameState:
        """
        Helper method to convert an observation to a GameState using reconstruction.

        Agents that prefer to work with GameState objects can use this method to
        reconstruct complete game states from observations.

        Args:
            observation: The observation to convert
            sampler: Optional custom sampler for hidden information.
                    If None, uses DefaultHiddenInfoSampler

        Returns:
            A reconstructed GameState

        Example:
            >>> def get_action(self, observation: Observation) -> Action:
            >>>     game_state = self.to_game_state(observation)
            >>>     # Now use game_state for planning...
        """
        from core.game_state_reconstructor import (
            GameStateReconstructor,
            DefaultHiddenInfoSampler
        )

        effective_sampler = sampler or DefaultHiddenInfoSampler(self.params)
        reconstructor = GameStateReconstructor(effective_sampler)
        return reconstructor.reconstruct(observation)
