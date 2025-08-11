from __future__ import annotations  # For forward references in type hints

import re
import math
from enum import Enum
from typing import List, Optional, ClassVar
from pydantic import BaseModel, Field, ConfigDict


# --- Helper functions for camelCase <-> snake_case ---

def camel_to_snake(name: str) -> str:
    return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()


def snake_to_camel(name: str) -> str:
    parts = name.split('_')
    return parts[0] + ''.join(word.capitalize() for word in parts[1:])


# --- Base model for camelCase JSON support ---

class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=snake_to_camel,
        populate_by_name=True,
        extra='forbid'  # helps catch unexpected fields
    )


# --- Enums ---

class Player(str, Enum):
    Player1 = "Player1"
    Player2 = "Player2"
    Neutral = "Neutral"

    def opponent(self) -> Player:
        if self == Player.Player1:
            return Player.Player2
        elif self == Player.Player2:
            return Player.Player1
        else:
            raise ValueError("Neutral has no opponent")


# --- Data classes ---

# class Vec2d(CamelModel):
#     x: float
#     y: float
#

class Vec2d(CamelModel):
    x: float = Field(default=0.0)
    y: float = Field(default=0.0)

    def __add__(self, other: 'Vec2d') -> 'Vec2d':
        return Vec2d(x=self.x + other.x, y=self.y + other.y)

    def __sub__(self, other: 'Vec2d') -> 'Vec2d':
        return Vec2d(x=self.x - other.x, y=self.y - other.y)

    def __mul__(self, scalar: float) -> 'Vec2d':
        return Vec2d(x=self.x * scalar, y=self.y * scalar)

    def dot(self, other: 'Vec2d') -> float:
        return self.x * other.x + self.y * other.y

    def w_add(self, other: 'Vec2d', scalar: float) -> 'Vec2d':
        return Vec2d(x=self.x + other.x * scalar, y=self.y + other.y * scalar)

    def mag(self) -> float:
        return math.sqrt(self.x ** 2 + self.y ** 2)

    def distance(self, other: 'Vec2d') -> float:
        return (self - other).mag()

    def angle(self) -> float:
        return math.atan2(self.y, self.x)

    def rotate(self, angle: float) -> 'Vec2d':
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        return Vec2d(
            x=self.x * cos_a - self.y * sin_a,
            y=self.x * sin_a + self.y * cos_a
        )

    def rotated_by(self, theta: float) -> 'Vec2d':
        return self.rotate(theta)

    def normalize(self) -> 'Vec2d':
        magnitude = self.mag()
        return self * (1.0 / magnitude) if magnitude > 0 else self


class Transporter(CamelModel):
    s: Vec2d
    v: Vec2d
    owner: Player
    source_index: int
    destination_index: int
    n_ships: float


class Planet(CamelModel):
    owner: Player
    n_ships: float
    position: Vec2d
    growth_rate: float
    radius: float
    transporter: Optional[Transporter] = None
    id: int = Field(default=-1)


class GameState(CamelModel):
    planets: List[Planet]
    game_tick: int = Field(default=0)


class GameParams(CamelModel):
    # Spatial parameters
    width: int = Field(default=640)
    height: int = Field(default=480)
    edge_separation: float = Field(default=25.0)
    radial_separation: float = Field(default=1.5)
    growth_to_radius_factor: float = Field(default=200.0)

    # Game parameters
    num_planets: int = Field(default=10)
    initial_neutral_ratio: float = Field(default=0.5)
    max_ticks: int = Field(default=2000)
    min_initial_ships_per_planet: int = Field(default=2)
    max_initial_ships_per_planet: int = Field(default=20)
    min_growth_rate: float = Field(default=0.02)
    max_growth_rate: float = Field(default=0.1)
    transporter_speed: float = Field(default=3.0)

    # Meta game parameters
    new_map_each_run: bool = Field(default=True)


class Action(CamelModel):
    player_id: Player
    source_planet_id: int
    destination_planet_id: int
    num_ships: float

    # ClassVar ensures Pydantic skips this during validation
    DO_NOTHING: ClassVar[Action]  # assigned below

    @staticmethod
    def do_nothing() -> Action:
        return Action.DO_NOTHING


# Assign DO_NOTHING after the Action class is defined
Action.DO_NOTHING = Action(
    player_id=Player.Neutral,
    source_planet_id=-1,
    destination_planet_id=-1,
    num_ships=0.0
)

if __name__ == "__main__":
    # Example usage
    game_params = GameParams()
    print(game_params.model_dump(by_alias=True))

    action = Action(
        player_id=Player.Player1,
        source_planet_id=1,
        destination_planet_id=2,
        num_ships=10.0
    )
    print(action.model_dump(by_alias=True))
    print()
    print(action.model_dump(by_alias=True, mode="json"))
