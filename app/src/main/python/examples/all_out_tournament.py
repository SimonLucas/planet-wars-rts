# ==============================================================================
# FILE: examples/all_out_tournament.py
# ==============================================================================
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
python_root = os.path.abspath(os.path.join(current_dir, ".."))
if python_root not in sys.path:
    sys.path.insert(0, python_root)

from core.unified_game_runner import UnifiedGameRunner
from core.game_state import GameParams, Player
from agents.random_agents import CarefulRandomAgent
from agents.greedy_heuristic_agent import GreedyHeuristicAgent
from agents.dqn_intuition_agent import dqn_intuition_agent
from agents.score_dqn_bot import score_dqn_bot
from agents.dqn_defense_agent import DQN_Defense_Agent
from agents.dqn_defense_multi_simulation_agent import DQN_Defense_Multi_Simulation_Agent
from agents.team_titans_pure_agent import TeamTitansPureAgent
from agents.fully_observable_agent_adapter import as_unified

def run_grand_tournament():
    print("█" * 80)
    print("🛸   THE ULTIMATE ALL-OUT DQNDEFENCE & VARIANT TOURNAMENT SYSTEM   🛸")
    print("█" * 80)

    game_params = GameParams(num_planets=20, max_ticks=500, new_map_each_run=True)

    # Hardcoded model path update as specified by the user
    fixed_model_path = "/workspaces/planet-wars-rts/app/src/main/python/agents/planet_wars_dqn.pt"

    # Instantiate all active players up front with the required absolute checkpoint paths
    registry = {
        "GreedyHeuristic": {"agent": GreedyHeuristicAgent(), "group": "others"},
        "DQN_Defense_Multi_Simulation_Agent": {"agent": DQN_Defense_Multi_Simulation_Agent(model_path=fixed_model_path), "group": "defense"},
    }

    sets_count = 3
    games_per_set = 10
    total_games_per_matchup = sets_count * games_per_set

    # Track independent statistics for full observability and partial observability modes
    full_obs_leaderboard = {name: {"wins": 0, "losses": 0, "games_played": 0} for name in registry.keys()}
    partial_obs_leaderboard = {name: {"wins": 0, "losses": 0, "games_played": 0} for name in registry.keys()}

    for obs_mode in [False, True]:
        label_str = "PARTIALLY OBSERVABLE MODE" if obs_mode else "FULLY OBSERVABLE MODE"
        current_leaderboard = partial_obs_leaderboard if obs_mode else full_obs_leaderboard
        
        print("\n" + "=" * 80)
        print(f"🔥 CURRENT ARENA ENVIRONMENT: {label_str}")
        print("=" * 80)

        agent_names = list(registry.keys())
        for i in range(len(agent_names)):
            for j in range(i, len(agent_names)):
                name1 = agent_names[i]
                name2 = agent_names[j]

                # Skip self-play completely
                if name1 == name2:
                    continue

                # Filter Rule: The 4 'others' agents should NOT play among themselves.
                # Only allow matchups if at least one agent belongs to the 'defense' group.
                if registry[name1]["group"] == "others" and registry[name2]["group"] == "others":
                    continue

                print(f"\n⚔️  Matchup: {name1} vs {name2} ({total_games_per_matchup} games scheduled)")
                
                m1_wins = 0
                m2_wins = 0

                for s in range(sets_count):
                    for g in range(games_per_set):
                        if g % 2 == 0:
                            p1_name, p2_name = name1, name2
                            p1_agent, p2_agent = registry[name1]["agent"], registry[name2]["agent"]
                        else:
                            p1_name, p2_name = name2, name1
                            p1_agent, p2_agent = registry[name2]["agent"], registry[name1]["agent"]

                        runner = UnifiedGameRunner(
                            as_unified(p1_agent), 
                            as_unified(p2_agent), 
                            game_params, 
                            partial_observability=obs_mode
                        )
                        fm = runner.run_game()
                        winner = fm.get_leader()

                        if winner == Player.Player1:
                            if p1_name == name1: m1_wins += 1
                            else: m2_wins += 1
                        elif winner == Player.Player2:
                            if p2_name == name1: m1_wins += 1
                            else: m2_wins += 1

                current_leaderboard[name1]["wins"] += m1_wins
                current_leaderboard[name1]["losses"] += m2_wins
                current_leaderboard[name1]["games_played"] += total_games_per_matchup

                current_leaderboard[name2]["wins"] += m2_wins
                current_leaderboard[name2]["losses"] += m1_wins
                current_leaderboard[name2]["games_played"] += total_games_per_matchup

                win_rate1 = (m1_wins / total_games_per_matchup) * 100
                win_rate2 = (m2_wins / total_games_per_matchup) * 100
                print(f"   📊 Results: {name1} ({win_rate1:.1f}%)  |  {name2} ({win_rate2:.1f}%)")

    # Final Complete Leaderboards Output Report segmented by observability conditions
    for mode_title, lboard in [("FULLY OBSERVABLE MODE", full_obs_leaderboard), ("PARTIALLY OBSERVABLE MODE", partial_obs_leaderboard)]:
        print("\n" + "█" * 80)
        print(f"🏆   GRAND TOURNAMENT LEADERBOARD: {mode_title}   🏆")
        print("█" * 80)
        
        sorted_stats = []
        for name, stats in lboard.items():
            w = stats["wins"]
            t = stats["games_played"]
            wr = (w / t) * 100 if t > 0 else 0.0
            sorted_stats.append((name, w, stats["losses"], t, wr))
        
        sorted_stats.sort(key=lambda x: x[4], reverse=True)

        for rank, (name, wins, losses, total, wr) in enumerate(sorted_stats, start=1):
            crown = "🥇" if rank == 1 else ("🥈" if rank == 2 else ("🥉" if rank == 3 else "🚀"))
            group_flag = "[Defense Family]" if registry[name]["group"] == "defense" else "[Opponent Profile]"
            print(f" #{rank} {crown} {name:<36} {group_flag:<18} | Win Rate: {wr:>5.1f}% | Total Match Record: {wins}W - {losses}L (Out of {total} Matches)")
        print("█" * 80)

if __name__ == '__main__':
    run_grand_tournament()