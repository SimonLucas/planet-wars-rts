import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from league.league_schema import Base, Match
from league.round_robin_top_n import compute_head_to_head
from league.cog_2026_config import selected_names
from league.export_cog_results import overall


class CogRoundRobinTest(unittest.TestCase):
    def test_old_league_results_do_not_leak_into_corrected_run(self):
        engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            for league, winner in [(5, 1), (5, 1), (6, 2)]:
                session.add(Match(league_id=league, player1_id=1, player2_id=2,
                                  winner_id=winner, map_name='test', seed=0,
                                  game_params={}, player1_score=int(winner == 1),
                                  player2_score=int(winner == 2), log_url=''))
            session.commit()
            self.assertEqual(compute_head_to_head(session, 6, [1, 2]),
                             {(1, 2): (0, 1), (2, 1): (1, 1)})

    def test_variant_filter_recomputes_against_remaining_opponents(self):
        self.assertEqual(len(selected_names()), 10)
        self.assertEqual(len(set(selected_names())), 10)
        self.assertNotIn('metagross-efaebe5', selected_names())
        self.assertIn('metang-6ac59b9', selected_names())
        self.assertEqual(len(selected_names('metagross')), 10)
        self.assertNotIn('metang-6ac59b9', selected_names('metagross'))
        self.assertIn('metagross-efaebe5', selected_names('metagross'))
        h2h = {(1, 2): (0, 20), (1, 3): (10, 10)}
        self.assertEqual(overall(1, [1, 2, 3], h2h), 0.5)
        self.assertEqual(overall(1, [1, 3], h2h), 1.0)
        self.assertEqual(overall(1, [1, 4], h2h), -1.0)


if __name__ == '__main__':
    unittest.main()
