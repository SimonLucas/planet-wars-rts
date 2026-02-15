"""
Observation module for partially observable Planet Wars games.

This module provides classes for representing partial observations of the game state,
where some information (like opponent ship counts) may be hidden from the observing player.
"""

from __future__ import annotations
from typing import Optional, Set, List
from pydantic import Field

from core.game_state import CamelModel, Vec2d, Player, GameState, Planet, Transporter


class TransporterObservation(CamelModel):
    """
    Observation of a transporter with potentially hidden information.

    In partially observable games, the number of ships in opponent transporters
    may be hidden (None). In fully observable games, all fields are populated.
    """
    s: Vec2d
    v: Vec2d
    owner: Player
    source_index: int
    destination_index: int
    n_ships: Optional[float] = None  # None = hidden information


class PlanetObservation(CamelModel):
    """
    Observation of a planet with potentially hidden information.

    In partially observable games:
    - Own planets: all information visible
    - Opponent/neutral planets: n_ships is None (hidden)

    In fully observable games, all fields are populated.
    """
    owner: Player
    n_ships: Optional[float] = None  # None = hidden information
    position: Vec2d
    growth_rate: float
    radius: float
    transporter: Optional[TransporterObservation] = None
    id: int


class Observation(CamelModel):
    """
    Complete observation of the game state from a player's perspective.

    Contains a list of planet observations where some information may be hidden
    depending on the observability mode and which player is observing.
    """
    observed_planets: List[PlanetObservation]
    game_tick: int = Field(default=0)


class ObservationFactory:
    """
    Factory for creating Observations from GameStates.

    Generates observations with appropriate visibility based on which players
    are observing. Information belonging to non-observing players can be hidden.
    """

    @staticmethod
    def create(
        game_state: GameState,
        observers: Set[Player],
        include_transporter_locations: bool = True
    ) -> Observation:
        """
        Create an observation from a game state for specific observers.

        Args:
            game_state: The complete game state to observe
            observers: Set of players who can see the information (e.g., {Player.Player1})
                      For fully observable: {Player.Player1, Player.Player2, Player.Neutral}
            include_transporter_locations: Whether to include transporter positions
                                          (even if ship counts are hidden)

        Returns:
            Observation with hidden information for non-observed players

        Examples:
            # Partially observable for Player1
            obs = ObservationFactory.create(game_state, {Player.Player1})

            # Fully observable (all players can see everything)
            obs = ObservationFactory.create(
                game_state,
                {Player.Player1, Player.Player2, Player.Neutral}
            )
        """
        observed_planets: List[PlanetObservation] = []

        for planet in game_state.planets:
            if planet.owner in observers:
                # Full visibility for owned planets
                transporter_obs = None
                if planet.transporter is not None:
                    trans = planet.transporter
                    # Show transporter details if owned or if locations should be included
                    if trans.owner in observers or include_transporter_locations:
                        transporter_obs = TransporterObservation(
                            s=trans.s,
                            v=trans.v,
                            owner=trans.owner,
                            source_index=trans.source_index,
                            destination_index=trans.destination_index,
                            n_ships=trans.n_ships if trans.owner in observers else None
                        )

                observed_planets.append(PlanetObservation(
                    owner=planet.owner,
                    n_ships=planet.n_ships,
                    position=planet.position,
                    growth_rate=planet.growth_rate,
                    radius=planet.radius,
                    transporter=transporter_obs,
                    id=planet.id
                ))
            else:
                # Limited visibility for unowned planets
                transporter_obs = None
                if planet.transporter is not None and include_transporter_locations:
                    trans = planet.transporter
                    transporter_obs = TransporterObservation(
                        s=trans.s,
                        v=trans.v,
                        owner=trans.owner,
                        source_index=trans.source_index,
                        destination_index=trans.destination_index,
                        n_ships=None  # Hidden for opponent transporters
                    )

                observed_planets.append(PlanetObservation(
                    owner=planet.owner,
                    n_ships=None,  # Hide ship count for opponent/neutral planets
                    position=planet.position,
                    growth_rate=planet.growth_rate,
                    radius=planet.radius,
                    transporter=transporter_obs,
                    id=planet.id
                ))

        return Observation(
            observed_planets=observed_planets,
            game_tick=game_state.game_tick
        )


# Example usage
if __name__ == "__main__":
    from core.game_state_factory import GameStateFactory
    from core.game_state import GameParams

    # Create a sample game state
    params = GameParams(num_planets=5)
    game_state = GameStateFactory(params).create_game()

    # Create partially observable observation for Player1
    partial_obs = ObservationFactory.create(game_state, {Player.Player1})
    print("Partial Observation (Player1 only):")
    print(f"  Total planets observed: {len(partial_obs.observed_planets)}")

    # Count visible vs hidden ship counts
    visible = sum(1 for p in partial_obs.observed_planets if p.n_ships is not None)
    hidden = sum(1 for p in partial_obs.observed_planets if p.n_ships is None)
    print(f"  Planets with visible ships: {visible}")
    print(f"  Planets with hidden ships: {hidden}")

    # Create fully observable observation
    full_obs = ObservationFactory.create(
        game_state,
        {Player.Player1, Player.Player2, Player.Neutral}
    )
    print("\nFully Observable (all players):")
    print(f"  Total planets observed: {len(full_obs.observed_planets)}")
    visible_all = sum(1 for p in full_obs.observed_planets if p.n_ships is not None)
    print(f"  All planets visible: {visible_all == len(full_obs.observed_planets)}")
