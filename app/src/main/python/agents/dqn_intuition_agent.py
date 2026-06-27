# ==============================================================================
# FILE: agents/dqn_intuition_agent.py
# ==============================================================================
import os
import sys
import math
import random
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from core.game_state import GameState, Action, Player
from core.forward_model import ForwardModel
from agents.planet_wars_agent import PlanetWarsPlayer
from agents.greedy_heuristic_agent import GreedyHeuristicAgent

class TitansDQN(nn.Module):
    def __init__(self, n_observations, n_actions):
        super().__init__()
        self.layer1 = nn.Linear(n_observations, 256)
        self.layer2 = nn.Linear(256, 256)
        self.layer3 = nn.Linear(256, n_actions)
        self.value_head = nn.Linear(256, 1)

    def forward(self, x):
        h2 = F.relu(self.layer2(F.relu(self.layer1(x))))
        q_values = self.layer3(h2)
        value = torch.tanh(self.value_head(h2))
        return q_values, value

class dqn_intuition_agent(PlanetWarsPlayer):
    def __init__(self, model_path=None):
        super().__init__()
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        if model_path is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            self.model_path = os.path.join(current_dir, "planet_wars_dqn.pt")
        else:
            self.model_path = model_path

        self.num_planets = 10
        self.n_observations = self.num_planets * 7
        self.n_actions = self.num_planets * self.num_planets
        self.horizon_ticks = 60

        # Weights configuration
        self.dqn_blend_weight = 0.3
        self.heuristic_weight = 0.7
        
        # NOTE: This scale factor rescales bounded [-1, 1] values to the heuristic scale.
        self.dqn_scale_factor = 100.0 

        self.policy_net = TitansDQN(self.n_observations, self.n_actions).to(self.device)

        if os.path.exists(self.model_path):
            try:
                state_dict = torch.load(self.model_path, map_location=self.device)
                filtered_dict = {k: v for k, v in state_dict.items() if k in self.policy_net.state_dict()}
                self.policy_net.load_state_dict(filtered_dict, strict=False)
                self.policy_net.eval()
                print(f"✅ dqn_intuition_agent successfully loaded weights from {self.model_path}")
            except Exception as e:
                print(f"⚠️ Warning: Failed loading state_dict in dqn_intuition_agent ({e})")
        else:
            print(f"📡 dqn_intuition_agent checkpoint not found at {self.model_path}. Running default random weights.")

    def prepare_to_play_as(self, player: Player, params, *args, **kwargs) -> None:
        super().prepare_to_play_as(player, params, *args, **kwargs)
        self.player = player
        self.params = params

    def _unknown_planet_count(self, game_state: GameState):
        return sum(1 for planet in game_state.planets if planet.n_ships is None)

    def _safe_n_ships(self, n_ships, growth_rate, current_tick, unknown_planet_count=0, owner=None):
        if n_ships is None:
            uncertainty_multiplier = min(2.0, 1.0 + 0.1 * float(unknown_planet_count))
            baseline = 10.0
            if owner == Player.Neutral or owner == "Neutral":
                return min(150.0, baseline * uncertainty_multiplier)
            else:
                return min(150.0, (baseline + float(growth_rate) * float(current_tick)) * uncertainty_multiplier)
        return float(n_ships)

    def _is_attack_viable(self, src_planet, dest_planet, src_ships, dest_ships):
        if dest_planet.owner == self.player:
            return True
        distance = src_planet.position.distance(dest_planet.position)
        eta = distance / self.params.transporter_speed if self.params else (distance / 2.0)
        estimated_defense = dest_ships + dest_planet.growth_rate * eta
        return src_ships > estimated_defense

    def _compute_pressures_and_etas(self, game_state: GameState):
        current_tick = getattr(game_state, 'game_tick', 0)
        unknown_planet_count = self._unknown_planet_count(game_state)
        incoming_friendly_pressure = {i: 0.0 for i in range(self.num_planets)}
        incoming_enemy_pressure = {i: 0.0 for i in range(self.num_planets)}
        min_enemy_eta = {i: float('inf') for i in range(self.num_planets)}

        for p_src in game_state.planets:
            transporter = getattr(p_src, 'transporter', None)
            if transporter is not None:
                dest_id = getattr(transporter, 'destination_index', None)
                owner = getattr(transporter, 'owner', None)
                ships = self._safe_n_ships(getattr(transporter, 'n_ships', None), getattr(p_src, 'growth_rate', 1.0), current_tick, unknown_planet_count, owner=owner)
                pos = getattr(transporter, 's', None)
                vel = getattr(transporter, 'v', None)

                if dest_id is not None and dest_id < self.num_planets:
                    dest_planet = game_state.planets[dest_id]
                    if pos is not None and vel is not None:
                        distance_remaining = pos.distance(dest_planet.position)
                        speed = vel.mag()
                        eta = distance_remaining / speed if speed > 0.01 else 1.0
                    else:
                        distance_remaining = p_src.position.distance(dest_planet.position)
                        eta = distance_remaining / (self.params.transporter_speed if self.params else 2.0)
                    
                    pressure_val = ships / (eta + 1.0)
                    if owner == self.player:
                        incoming_friendly_pressure[dest_id] += pressure_val
                    else:
                        incoming_enemy_pressure[dest_id] += pressure_val
                        if eta < min_enemy_eta[dest_id]:
                            min_enemy_eta[dest_id] = eta
        return incoming_friendly_pressure, incoming_enemy_pressure, min_enemy_eta

    def _state_to_tensor(self, game_state: GameState, precomputed_pressures=None) -> torch.Tensor:
        state_list = []
        max_x = getattr(self.params, 'width', 25.0) if self.params else 25.0
        max_y = getattr(self.params, 'height', 25.0) if self.params else 25.0
        current_tick = getattr(game_state, 'game_tick', 0)
        unknown_planet_count = self._unknown_planet_count(game_state)

        if precomputed_pressures is not None:
            friendly_p, enemy_p = precomputed_pressures
        else:
            friendly_p, enemy_p, _ = self._compute_pressures_and_etas(game_state)

        for i in range(self.num_planets):
            if i < len(game_state.planets):
                p = game_state.planets[i]
                owner_val = 1.0 if p.owner == self.player else (-1.0 if p.owner == self.player.opponent() else 0.0)
                n_ships_val = self._safe_n_ships(p.n_ships, p.growth_rate, current_tick, unknown_planet_count, owner=p.owner)
                state_list.extend([owner_val, n_ships_val / 100.0, p.growth_rate, p.position.x / max_x, p.position.y / max_y, friendly_p[i], enemy_p[i]])
            else:
                state_list.extend([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        return torch.tensor(state_list, dtype=torch.float32, device=self.device).unsqueeze(0)

    def get_action(self, game_state: GameState) -> Action:
        my_planets = [p for p in game_state.planets if p.owner == self.player and p.n_ships is not None and p.n_ships > 1]
        if not my_planets or len(game_state.planets) > self.num_planets:
            return Action.do_nothing()

        friendly_p, enemy_p, min_enemy_eta = self._compute_pressures_and_etas(game_state)
        current_tick = getattr(game_state, 'game_tick', 0)
        unknown_planet_count = self._unknown_planet_count(game_state)
        
        candidates = []

        # Instantiate live agents to generate ongoing tactical decisions inside rollout simulations
        self_heuristic = GreedyHeuristicAgent()
        self_heuristic.prepare_to_play_as(self.player, self.params)

        opp_heuristic = GreedyHeuristicAgent()
        opp_heuristic.prepare_to_play_as(self.player.opponent(), self.params)

        for src_id, src_planet in enumerate(game_state.planets):
            if src_planet.owner != self.player or src_planet.n_ships is None or src_planet.n_ships <= 1:
                continue
            
            src_ships = self._safe_n_ships(src_planet.n_ships, src_planet.growth_rate, current_tick, unknown_planet_count, owner=src_planet.owner)

            for dest_id, dest_planet in enumerate(game_state.planets):
                if src_id == dest_id:
                    continue

                if dest_planet.owner == self.player and enemy_p.get(dest_id, 0.0) <= 0:
                    continue

                dest_ships = self._safe_n_ships(dest_planet.n_ships, dest_planet.growth_rate, current_tick, unknown_planet_count, owner=dest_planet.owner)

                if not self._is_attack_viable(src_planet, dest_planet, src_ships, dest_ships):
                    continue

                distance = src_planet.position.distance(dest_planet.position)
                eta = distance / self.params.transporter_speed if self.params else (distance / 2.0)

                if dest_planet.owner == Player.Neutral:
                    payload = (dest_ships * 1.1) + 1.0
                elif dest_planet.owner == self.player:
                    payload = src_ships * 0.30
                else:
                    payload = src_ships * 0.75
                    real_defense = dest_ships + dest_planet.growth_rate * eta
                    if payload <= real_defense:
                        payload = min(real_defense + 5.0, src_ships - 5.0)

                if payload <= 0 or (src_ships - payload) < 5.0 or payload > src_ships:
                    continue

                candidate_action = Action(
                    player_id=self.player,
                    source_planet_id=src_id,
                    destination_planet_id=dest_id,
                    num_ships=float(payload)
                )
                candidates.append(candidate_action)

        if not candidates:
            return Action.do_nothing()

        best_action = None
        best_score = -float('inf')

        for candidate_action in candidates:
            cloned_state = game_state.model_copy(deep=True)
            fm = ForwardModel(cloned_state, self.params)
            
            # Step 1: Candidate move vs active opponent response
            fm.step({self.player: candidate_action, self.player.opponent(): opp_heuristic.get_action(fm.state)})
            
            # Remaining ticks: Both agents continue evaluating actions dynamically via heuristic engines
            for _ in range(self.horizon_ticks - 1):
                if fm.is_terminal():
                    break
                fm.step({self.player: self_heuristic.get_action(fm.state), self.player.opponent(): opp_heuristic.get_action(fm.state)})

            if fm.is_terminal():
                leader = fm.get_leader()
                if leader == self.player:
                    heuristic_score = 999.0
                elif leader == self.player.opponent():
                    heuristic_score = -999.0
                else:
                    heuristic_score = 0.0
                
                dqn_score = 0.0
            else:
                sim_tick = fm.state.game_tick
                sim_unknown_count = self._unknown_planet_count(fm.state)
                my_total_ships = sum(self._safe_n_ships(p.n_ships, p.growth_rate, sim_tick, sim_unknown_count, owner=p.owner) for p in fm.state.planets if p.owner == self.player)
                opp_total_ships = sum(self._safe_n_ships(p.n_ships, p.growth_rate, sim_tick, sim_unknown_count, owner=p.owner) for p in fm.state.planets if p.owner == self.player.opponent())
                my_total_growth = sum(p.growth_rate for p in fm.state.planets if p.owner == self.player)
                opp_total_growth = sum(p.growth_rate for p in fm.state.planets if p.owner == self.player.opponent())
                
                heuristic_score = (my_total_ships - opp_total_ships) + 10.0 * (my_total_growth - opp_total_growth)

                end_state_tensor = self._state_to_tensor(fm.state)
                with torch.no_grad():
                    _, value = self.policy_net(end_state_tensor)
                    dqn_value = value.item()
                
                dqn_score = dqn_value * self.dqn_scale_factor

            final_score = (self.heuristic_weight * heuristic_score) + (self.dqn_blend_weight * dqn_score)

            if final_score > best_score:
                best_score = final_score
                best_action = candidate_action

        if best_action is not None:
            return best_action

        return Action.do_nothing()

    def get_agent_type(self) -> str:
        return "dqn_intuition_agent (DQN-Blended Heuristic / Uncertainty-Aware)"