# ==================================================
# 📄 agents/planet_wars_mcts.py
# ==================================================
import os
import sys
import math
import random
import numpy as np
import torch
from core.game_state import GameState, Action, Player
from core.forward_model import ForwardModel
from agents.greedy_heuristic_agent import GreedyHeuristicAgent
from agents.random_agents import CarefulRandomAgent

class PlanetWarsMCTS:
    def __init__(self, agent, params):
        self.agent = agent
        self.params = params
        self.num_planets = agent.num_planets
        self.n_actions = agent.n_actions
        
        self.Qsa = {}       
        self.Nsa = {}       
        self.Ns = {}        
        self.Ps = {}        
        
        # Fixed opponent instances to avoid instantiation overhead
        self.greedy_opp = GreedyHeuristicAgent()
        self.random_opp = CarefulRandomAgent()
        self._cached_opp_player_id = None
        
        # Fast self-play stub for lookahead simulations (bypasses MCTS recursion safely)
        class SelfPlayOpponent:
            def __init__(self, outer_agent):
                self.outer_agent = outer_agent
            def prepare_to_play_as(self, pid, prms):
                pass
            def get_action(self, game_state):
                friendly_p, enemy_p, _ = self.outer_agent.compute_pressures_and_etas(game_state)
                state_tensor = self.outer_agent.state_to_tensor(game_state, precomputed_pressures=(friendly_p, enemy_p))
                probs, _ = self.outer_agent.predict(state_tensor)
                if len(probs) == 0 or np.sum(probs) == 0:
                    return Action.do_nothing()
                act_idx = int(np.argmax(probs))
                s_id = act_idx // self.outer_agent.num_planets
                d_id = act_idx % self.outer_agent.num_planets
                if s_id < len(game_state.planets) and d_id < len(game_state.planets):
                    src_p = game_state.planets[s_id]
                    if src_p.n_ships is not None and src_p.n_ships > 1:
                        payload = max(1.0, float(int(src_p.n_ships * 0.5)))
                        return Action(player_id=src_p.owner, source_planet_id=s_id, destination_planet_id=d_id, num_ships=payload)
                return Action.do_nothing()
                
        self.self_play_opp = SelfPlayOpponent(self.agent)
        
        # Safe unknown opponent fallback to avoid incorrect behavior against unknown agents
        class UnknownOpponent:
            def prepare_to_play_as(self, player_id, params):
                pass
            def get_action(self, game_state):
                return Action.do_nothing()
        self.unknown_opp = UnknownOpponent()
        
        # Default to a robust, strategy-agnostic blend matching tournament conditions
        self.current_opponent_type = "blended"

    def reset(self):
        self.Qsa.clear()
        self.Nsa.clear()
        self.Ns.clear()
        self.Ps.clear()
        
    def _rollout_depth(self, game_state: GameState) -> int:
        current_tick = getattr(game_state, 'game_tick', 0)
        max_ticks = max(1, getattr(self.params, 'max_ticks', 500))
        progress = min(1.0, max(0.0, float(current_tick) / float(max_ticks)))
        if progress < 0.35:
            return 1
        if progress < 0.75:
            return 2
        return 3

    def set_opponent_context(self, opponent_type: str):
        self.current_opponent_type = opponent_type

    def get_opponent_instance(self, player_id):
        # Cache initialization to prevent preparing objects thousands of times per turn
        if self._cached_opp_player_id != player_id:
            self.greedy_opp.prepare_to_play_as(player_id, self.params)
            self.random_opp.prepare_to_play_as(player_id, self.params)
            self._cached_opp_player_id = player_id

        if self.current_opponent_type == "blended":
            roll = random.random()
            if roll < 0.60:
                return self.self_play_opp
            elif roll < 0.80:
                return self.greedy_opp
            else:
                return self.random_opp
        elif self.current_opponent_type == "greedy":
            return self.greedy_opp
        elif self.current_opponent_type == "random":
            return self.random_opp
        else:
            return self.unknown_opp

    def stringRepresentation(self, game_state: GameState) -> str:
        sb = []
        for p in game_state.planets:
            rounded_ships = int(round(p.n_ships / 10.0) * 10)
            sb.append(f"{p.id}:{p.owner.value}:{rounded_ships}")
        return "|".join(sb)

    def getActionProb(self, game_state: GameState, temp=0) -> int:
        s = self.stringRepresentation(game_state)
        mcts_sims = getattr(self.agent, 'mcts_sims', 15)
        
        for _ in range(mcts_sims):
            self.search(game_state.model_copy(deep=True), depth=0)

        counts = [self.Nsa.get((s, a), 0) for a in range(self.n_actions)]
        counts_arr = np.array(counts, dtype=np.float32)
        
        if np.sum(counts_arr) == 0:
            friendly_p, enemy_p, _ = self.agent.compute_pressures_and_etas(game_state)
            state_tensor = self.agent.state_to_tensor(game_state, precomputed_pressures=(friendly_p, enemy_p))
            probs, _ = self.agent.predict(state_tensor)
            
            mask = np.zeros(self.n_actions)
            current_tick = getattr(game_state, 'game_tick', 0)
            unknown_planet_count = sum(1 for planet in game_state.planets if planet.n_ships is None)
            for action_idx in range(self.n_actions):
                source_id = action_idx // self.num_planets
                dest_id = action_idx % self.num_planets
                if source_id < len(game_state.planets) and dest_id < len(game_state.planets):
                    src_p = game_state.planets[source_id]
                    dest_p = game_state.planets[dest_id]
                    if src_p.owner == self.agent.player and src_p.n_ships is not None and src_p.n_ships > 1 and source_id != dest_id:
                        if dest_p.owner == self.agent.player and enemy_p.get(dest_id, 0.0) <= 0:
                            continue
                        src_ships = self.agent._safe_n_ships(src_p.n_ships, src_p.growth_rate, current_tick, unknown_planet_count, owner=src_p.owner)
                        dest_ships = self.agent._safe_n_ships(dest_p.n_ships, dest_p.growth_rate, current_tick, unknown_planet_count, owner=dest_p.owner)
                        if dest_p.owner != self.agent.player and not self.agent._is_attack_viable(src_p, dest_p, src_ships, dest_ships):
                            continue
                        mask[action_idx] = 1.0
            masked_probs = probs * mask
            if np.sum(masked_probs) > 0:
                masked_probs /= np.sum(masked_probs)
                return int(np.argmax(masked_probs))
            return 0

        if temp == 0:
            bestAs = np.array(np.argwhere(counts_arr == np.max(counts_arr))).flatten()
            return int(random.choice(bestAs))

        counts_pow = counts_arr ** (1.0 / temp)
        sum_counts = np.sum(counts_pow)
        probs = counts_pow / sum_counts
        return int(np.random.choice(self.n_actions, p=probs))

    def search(self, game_state: GameState, depth=0) -> float:
        fm = ForwardModel(game_state, self.params)
        if fm.is_terminal():
            leader = fm.get_leader()
            if leader == self.agent.player:
                return 1.0
            elif leader == self.agent.player.opponent():
                return -1.0
            return 0.0

        mcts_rollout = self._rollout_depth(game_state)
        if depth >= mcts_rollout:
            friendly_p, enemy_p, _ = self.agent.compute_pressures_and_etas(fm.state)
            state_tensor = self.agent.state_to_tensor(fm.state, precomputed_pressures=(friendly_p, enemy_p))
            _, v_val = self.agent.predict(state_tensor)
            return v_val

        s = self.stringRepresentation(fm.state)

        if s not in self.Ps:
            friendly_p, enemy_p, _ = self.agent.compute_pressures_and_etas(fm.state)
            state_tensor = self.agent.state_to_tensor(fm.state, precomputed_pressures=(friendly_p, enemy_p))
            probs, v_val = self.agent.predict(state_tensor)
            
            mask = np.zeros(self.n_actions)
            has_valid = False
            current_tick = getattr(fm.state, 'game_tick', 0)
            unknown_planet_count = sum(1 for planet in fm.state.planets if planet.n_ships is None)

            for action_idx in range(self.n_actions):
                source_id = action_idx // self.num_planets
                dest_id = action_idx % self.num_planets
                if source_id < len(fm.state.planets) and dest_id < len(fm.state.planets):
                    src_p = fm.state.planets[source_id]
                    dest_p = fm.state.planets[dest_id]
                    if src_p.owner == self.agent.player and src_p.n_ships is not None and src_p.n_ships > 1 and source_id != dest_id:
                        if dest_p.owner == self.agent.player and enemy_p.get(dest_id, 0.0) <= 0:
                            continue
                        src_ships = self.agent._safe_n_ships(src_p.n_ships, src_p.growth_rate, current_tick, unknown_planet_count, owner=src_p.owner)
                        dest_ships = self.agent._safe_n_ships(dest_p.n_ships, dest_p.growth_rate, current_tick, unknown_planet_count, owner=dest_p.owner)
                        if dest_p.owner != self.agent.player and not self.agent._is_attack_viable(src_p, dest_p, src_ships, dest_ships):
                            continue
                        mask[action_idx] = 1.0
                        has_valid = True

            if not has_valid:
                mask[0] = 1.0

            probs = probs * mask
            sum_probs = np.sum(probs)
            if sum_probs > 0:
                probs /= sum_probs
            else:
                probs = mask / np.sum(mask)

            self.Ps[s] = probs
            self.Ns[s] = 0
            return v_val

        probs = self.Ps[s]
        best_u = -float('inf')
        best_act = 0
        Cpuct = 1.0

        for a in range(self.n_actions):
            q_val = self.Qsa[(s, a)] if (s, a) in self.Qsa else 0.0
            n_val = self.Nsa[(s, a)] if (s, a) in self.Nsa else 0
            u = q_val + Cpuct * probs[a] * math.sqrt(self.Ns[s] + 1e-8) / (1 + n_val)
            if u > best_u:
                best_u = u
                best_act = a

        source_id = best_act // self.num_planets
        dest_id = best_act % self.num_planets
        my_action = Action.do_nothing()
        current_tick = getattr(fm.state, 'game_tick', 0)
        unknown_planet_count = sum(1 for planet in fm.state.planets if planet.n_ships is None)

        if source_id < len(fm.state.planets) and dest_id < len(fm.state.planets):
            src_p = fm.state.planets[source_id]
            dest_p = fm.state.planets[dest_id]
            if src_p.owner == self.agent.player and src_p.n_ships is not None and src_p.n_ships > 1:
                src_ships = self.agent._safe_n_ships(src_p.n_ships, src_p.growth_rate, current_tick, unknown_planet_count, owner=src_p.owner)
                dest_ships = self.agent._safe_n_ships(dest_p.n_ships, dest_p.growth_rate, current_tick, unknown_planet_count, owner=dest_p.owner)

                if dest_p.owner == Player.Neutral:
                    payload = (dest_ships * 1.1) + 1.0
                elif dest_p.owner == self.agent.player:
                    payload = src_ships * 0.30
                else:
                    eta = src_p.position.distance(dest_p.position) / self.params.transporter_speed
                    real_defense = dest_ships + dest_p.growth_rate * eta
                    payload = min(real_defense + 5.0, src_ships - 5.0)

                if (src_ships - payload) >= 5.0:
                    final_payload = max(1.0, min(float(payload), float(src_ships - 1)))
                    my_action = Action(
                        player_id=self.agent.player,
                        source_planet_id=source_id,
                        destination_planet_id=dest_id,
                        num_ships=final_payload
                    )

        opp_agent = self.get_opponent_instance(self.agent.player.opponent())
        opp_action = opp_agent.get_action(fm.state)

        fm.step({self.agent.player: my_action, self.agent.player.opponent(): opp_action})
        v_val = self.search(fm.state, depth + 1)

        if (s, best_act) in self.Qsa:
            self.Qsa[(s, best_act)] = (self.Nsa[(s, best_act)] * self.Qsa[(s, best_act)] + v_val) / (self.Nsa[(s, best_act)] + 1)
            self.Nsa[(s, best_act)] += 1
        else:
            self.Qsa[(s, best_act)] = v_val
            self.Nsa[(s, best_act)] = 1

        self.Ns[s] += 1
        return v_val