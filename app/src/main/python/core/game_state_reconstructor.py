"""
Game state reconstruction from partial observations.

This module provides tools for reconstructing complete GameStates from Observations
that may contain hidden information. This is essential for agents that want to use
planning algorithms requiring complete game states in partially observable games.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Protocol
import random

from core.game_state import GameState, GameParams, Planet, Transporter
from core.observation import Observation


class HiddenInfoSampler(Protocol):
    """
    Protocol for sampling hidden information in partially observable games.

    Agents can implement custom samplers with sophisticated estimation strategies
    based on game history, probabilistic models, or learned heuristics.
    """

    def sample_ships(self) -> float:
        """
        Sample the number of ships for a planet with hidden information.

        Returns:
            Estimated number of ships
        """
        ...

    def sample_transporter_ships(self) -> float:
        """
        Sample the number of ships for a transporter with hidden information.

        Returns:
            Estimated number of ships
        """
        ...


class DefaultHiddenInfoSampler:
    """
    Default sampler that uses uniform random sampling within game parameter bounds.

    This is a simple baseline strategy. Advanced agents should implement custom
    samplers with better estimation strategies.
    """

    def __init__(self, params: GameParams):
        """
        Initialize with game parameters to determine sampling bounds.

        Args:
            params: Game parameters defining valid ranges
        """
        self.params = params

    def sample_ships(self) -> float:
        """
        Sample planet ship count uniformly within initial ship bounds.

        Returns:
            Random ship count in [min_initial_ships, max_initial_ships]
        """
        return random.uniform(
            self.params.min_initial_ships_per_planet,
            self.params.max_initial_ships_per_planet
        )

    def sample_transporter_ships(self) -> float:
        """
        Sample transporter ship count (typically less than planet capacity).

        Returns:
            Random ship count in [1, max_initial_ships/2]
        """
        return random.uniform(
            1.0,
            self.params.max_initial_ships_per_planet / 2
        )


class GameStateReconstructor:
    """
    Reconstructs complete GameStates from partial Observations.

    Uses a HiddenInfoSampler to fill in missing information (None values)
    in observations, allowing agents to work with complete game states even
    in partially observable environments.
    """

    def __init__(self, sampler: HiddenInfoSampler):
        """
        Initialize reconstructor with a hidden information sampler.

        Args:
            sampler: Strategy for sampling hidden information
        """
        self.sampler = sampler

    def reconstruct(self, observation: Observation) -> GameState:
        """
        Reconstruct a complete GameState from an Observation.

        All None values (hidden information) are replaced with sampled values
        from the configured HiddenInfoSampler.

        Args:
            observation: Partial observation with potentially hidden information

        Returns:
            Complete GameState with all information filled in

        Example:
            >>> sampler = DefaultHiddenInfoSampler(params)
            >>> reconstructor = GameStateReconstructor(sampler)
            >>> game_state = reconstructor.reconstruct(observation)
        """
        reconstructed_planets: List[Planet] = []

        for observed_planet in observation.observed_planets:
            # Sample ship count if hidden
            n_ships = (
                observed_planet.n_ships
                if observed_planet.n_ships is not None
                else self.sampler.sample_ships()
            )

            # Reconstruct transporter if present
            transporter = None
            if observed_planet.transporter is not None:
                obs_trans = observed_planet.transporter
                transporter_ships = (
                    obs_trans.n_ships
                    if obs_trans.n_ships is not None
                    else self.sampler.sample_transporter_ships()
                )

                transporter = Transporter(
                    s=obs_trans.s,
                    v=obs_trans.v,
                    owner=obs_trans.owner,
                    source_index=obs_trans.source_index,
                    destination_index=obs_trans.destination_index,
                    n_ships=transporter_ships
                )

            reconstructed_planets.append(Planet(
                owner=observed_planet.owner,
                n_ships=n_ships,
                position=observed_planet.position,
                growth_rate=observed_planet.growth_rate,
                radius=observed_planet.radius,
                transporter=transporter,
                id=observed_planet.id
            ))

        return GameState(
            planets=reconstructed_planets,
            game_tick=observation.game_tick
        )


# Example usage
if __name__ == "__main__":
    from core.game_state_factory import GameStateFactory
    from core.observation import ObservationFactory
    from core.game_state import Player

    # Create a sample game
    params = GameParams(num_planets=5)
    game_state = GameStateFactory(params).create_game()

    # Create partially observable observation for Player1
    observation = ObservationFactory.create(game_state, {Player.Player1})

    # Reconstruct game state using default sampler
    sampler = DefaultHiddenInfoSampler(params)
    reconstructor = GameStateReconstructor(sampler)
    reconstructed_state = reconstructor.reconstruct(observation)

    print("Original Game State:")
    print(f"  Planets: {len(game_state.planets)}")
    print(f"  Player1 ships: {sum(p.n_ships for p in game_state.planets if p.owner == Player.Player1):.1f}")
    print(f"  Player2 ships: {sum(p.n_ships for p in game_state.planets if p.owner == Player.Player2):.1f}")

    print("\nReconstructed Game State:")
    print(f"  Planets: {len(reconstructed_state.planets)}")
    print(f"  Player1 ships: {sum(p.n_ships for p in reconstructed_state.planets if p.owner == Player.Player1):.1f}")
    print(f"  Player2 ships (estimated): {sum(p.n_ships for p in reconstructed_state.planets if p.owner == Player.Player2):.1f}")

    print("\nNote: Player2 ship counts are estimated and will differ from actual values")
