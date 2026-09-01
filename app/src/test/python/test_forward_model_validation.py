import math
import unittest

from core.forward_model import ForwardModel
from core.game_state import Action, GameParams, Player
from core.game_state_factory import GameStateFactory


class TestForwardModelActionValidation(unittest.TestCase):
    def setUp(self):
        self.params = GameParams(
            min_initial_ships_per_planet=10,
            num_planets=2,
            initial_neutral_ratio=0.0,
        )
        self.state = GameStateFactory(self.params).create_game()
        self.model = ForwardModel(self.state, self.params)
        self.source = next(p for p in self.state.planets if p.owner == Player.Player1)
        self.target = next(p for p in self.state.planets if p.owner == Player.Player2)

    def test_invalid_actions_do_not_change_source_or_launch_transporter(self):
        initial_ships = self.source.n_ships
        invalid_actions = [
            Action(player_id=Player.Player1, source_planet_id=self.source.id,
                   destination_planet_id=self.target.id, num_ships=-1.0),
            Action(player_id=Player.Player1, source_planet_id=self.source.id,
                   destination_planet_id=self.target.id, num_ships=0.0),
            Action(player_id=Player.Player1, source_planet_id=self.source.id,
                   destination_planet_id=self.target.id, num_ships=math.nan),
            Action(player_id=Player.Player1, source_planet_id=self.source.id,
                   destination_planet_id=self.target.id, num_ships=math.inf),
            Action(player_id=Player.Player1, source_planet_id=-1,
                   destination_planet_id=self.target.id, num_ships=1.0),
            Action(player_id=Player.Player1, source_planet_id=len(self.state.planets),
                   destination_planet_id=self.target.id, num_ships=1.0),
            Action(player_id=Player.Player1, source_planet_id=self.source.id,
                   destination_planet_id=-1, num_ships=1.0),
            Action(player_id=Player.Player1, source_planet_id=self.source.id,
                   destination_planet_id=len(self.state.planets), num_ships=1.0),
        ]

        for action in invalid_actions:
            with self.subTest(action=action):
                self.model.apply_actions({Player.Player1: action})
                self.assertEqual(initial_ships, self.source.n_ships)
                self.assertIsNone(self.source.transporter)

    def test_finite_positive_action_remains_valid(self):
        initial_ships = self.source.n_ships
        ships_to_send = initial_ships / 2.0
        action = Action(
            player_id=Player.Player1,
            source_planet_id=self.source.id,
            destination_planet_id=self.target.id,
            num_ships=ships_to_send,
        )

        self.model.apply_actions({Player.Player1: action})

        self.assertEqual(initial_ships - ships_to_send, self.source.n_ships)
        self.assertEqual(ships_to_send, self.source.transporter.n_ships)


if __name__ == "__main__":
    unittest.main()
