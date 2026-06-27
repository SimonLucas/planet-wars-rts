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
        self.layer3 = nn.Linear(256, 128)
        self.q_head = nn.Linear(128, n_actions)
        self.value_head = nn.Linear(128, 1)

    def forward(self, x):
        # Step-by-step feature extraction through dense hidden layers
        h1 = F.relu(self.layer1(x))
        h2 = F.relu(self.layer2(h1))
        h3 = F.relu(self.layer3(h2))  # This brings it from 256 to 128 dimensions
        
        # Pass the 128-dimension tensor (h3) to the policy and value heads
        q_values = self.q_head(h3)
        value = torch.tanh(self.value_head(h3))
        return q_values, value
    
class DQN_Defense_Agent(PlanetWarsPlayer):
    def __init__(self, model_path=None):
        super().__init__()
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        if model_path is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            self.model_path = os.path.join(current_dir, "planet_wars_dqn.pt")
        else:
            self.model_path = model_path

        self.num_planets = 20
        self.n_observations = self.num_planets * 7
        self.n_actions = self.num_planets * self.num_planets
        self.horizon_ticks = 30

        self.policy_net = TitansDQN(self.n_observations, self.n_actions).to(self.device)

        if os.path.exists(self.model_path):
            try:
                state_dict = torch.load(self.model_path, map_location=self.device)
                filtered_dict = {k: v for k, v in state_dict.items() if k in self.policy_net.state_dict()}
                self.policy_net.load_state_dict(filtered_dict, strict=False)
                self.policy_net.eval()
                print(f"✅ DQN_Defense_Agent successfully loaded weights from {self.model_path}")
            except Exception as e:
                print(f"⚠️ Warning: Failed loading state_dict in DQN_Defense_Agent ({e})")
        else:
            print(f"📡 DQN_Defense_Agent checkpoint not found at {self.model_path}. Running default random layout.")

        # Fixed Issue 2: Pre-instantiate opponent agent to avoid high allocation/garbage collection overhead
        self.opp_agent = GreedyHeuristicAgent()

    def prepare_to_play_as(self, player: Player, params, *args, **kwargs) -> None:
        super().prepare_to_play_as(player, params, *args, **kwargs)
        self.player = player
        self.params = params
        # Fixed Issue 2: Prepare opponent instance once here
        self.opp_agent.prepare_to_play_as(self.player.opponent(), self.params)

    def _safe_n_ships(self, n_ships, growth_rate, current_tick):
        if n_ships is not None:
            return float(n_ships)
        return min(150.0, float(growth_rate) * float(current_tick) * 0.5)

    def _is_attack_viable(self, src_planet, dest_planet, src_ships, dest_ships):
        if dest_planet.owner == self.player:
            return True
        distance = src_planet.position.distance(dest_planet.position)
        eta = distance / self.params.transporter_speed if self.params else (distance / 2.0)
        estimated_defense = dest_ships + dest_planet.growth_rate * eta
        return src_ships > estimated_defense

    def _compute_pressures_and_etas(self, game_state: GameState):
        current_tick = getattr(game_state, 'game_tick', 0)
        incoming_friendly_pressure = {i: 0.0 for i in range(self.num_planets)}
        incoming_enemy_pressure = {i: 0.0 for i in range(self.num_planets)}
        min_enemy_eta = {i: float('inf') for i in range(self.num_planets)}

        for p_src in game_state.planets:
            transporter = getattr(p_src, 'transporter', None)
            if transporter is not None:
                dest_id = getattr(transporter, 'destination_index', None)
                owner = getattr(transporter, 'owner', None)
                ships = self._safe_n_ships(getattr(transporter, 'n_ships', 0), getattr(p_src, 'growth_rate', 1.0), current_tick)
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

        if precomputed_pressures is not None:
            friendly_p, enemy_p = precomputed_pressures
        else:
            friendly_p, enemy_p, _ = self._compute_pressures_and_etas(game_state)

        for i in range(self.num_planets):
            if i < len(game_state.planets):
                p = game_state.planets[i]
                owner_val = 1.0 if p.owner == self.player else (-1.0 if p.owner == self.player.opponent() else 0.0)
                n_ships_val = self._safe_n_ships(p.n_ships, p.growth_rate, current_tick)
                state_list.extend([owner_val, n_ships_val / 100.0, p.growth_rate, p.position.x / max_x, p.position.y / max_y, friendly_p[i], enemy_p[i]])
            else:
                state_list.extend([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        return torch.tensor(state_list, dtype=torch.float32, device=self.device).unsqueeze(0)

    def _get_simulation_action(self, game_state: GameState) -> Action:
        # Fixed Issue 1: Policy network evaluation tool used inside the horizon multi-step loop
        current_tick = getattr(game_state, 'game_tick', 0)
        state_tensor = self._state_to_tensor(game_state)
        
        with torch.no_grad():
            q_values, _ = self.policy_net(state_tensor)
            q_values = q_values.squeeze(0).clone()

        mask = torch.full_like(q_values, float('-inf'))
        has_candidates = False

        for action_idx in range(self.n_actions):
            source_id = action_idx // self.num_planets
            dest_id = action_idx % self.num_planets

            if source_id < len(game_state.planets) and dest_id < len(game_state.planets):
                if source_id != dest_id:
                    src_planet = game_state.planets[source_id]
                    if src_planet.owner == self.player and src_planet.n_ships is not None and src_planet.n_ships > 1:
                        mask[action_idx] = 0.0
                        has_candidates = True

        if not has_candidates:
            return Action.do_nothing()

        masked_q = q_values + mask
        best_action_idx = torch.argmax(masked_q).item()
        
        if masked_q[best_action_idx] == float('-inf'):
            return Action.do_nothing()

        source_id = best_action_idx // self.num_planets
        dest_id = best_action_idx % self.num_planets
        src_planet = game_state.planets[source_id]

        src_ships = self._safe_n_ships(src_planet.n_ships, src_planet.growth_rate, current_tick)
        ships_to_send = src_ships * 0.5
        if ships_to_send < 1.0:
            return Action.do_nothing()

        return Action(
            player_id=self.player,
            source_planet_id=source_id,
            destination_planet_id=dest_id,
            num_ships=float(ships_to_send)
        )

    def get_action(self, game_state: GameState) -> Action:
        my_planets = [p for p in game_state.planets if p.owner == self.player and p.n_ships is not None and p.n_ships > 1]
        if not my_planets or len(game_state.planets) > self.num_planets:
            return Action.do_nothing()

        friendly_p, enemy_p, min_enemy_eta = self._compute_pressures_and_etas(game_state)
        
        is_threatened = any(enemy_p.get(i, 0.0) > 0 for i, p in enumerate(game_state.planets) if p.owner == self.player)

        if is_threatened:
            return self._dqn_defense(game_state, friendly_p, enemy_p, min_enemy_eta)
        else:
            return self._titans_offense(game_state)

    def _dqn_defense(self, game_state: GameState, friendly_p, enemy_p, min_enemy_eta) -> Action:
        current_tick = getattr(game_state, 'game_tick', 0)
        state_tensor = self._state_to_tensor(game_state, precomputed_pressures=(friendly_p, enemy_p))
        
        with torch.no_grad():
            q_values, _ = self.policy_net(state_tensor)
            q_values = q_values.squeeze(0).clone()

        mask = torch.full_like(q_values, float('-inf'))
        has_candidates = False

        for action_idx in range(self.n_actions):
            source_id = action_idx // self.num_planets
            dest_id = action_idx % self.num_planets

            if source_id < len(game_state.planets) and dest_id < len(game_state.planets):
                if source_id != dest_id:
                    src_planet = game_state.planets[source_id]
                    dest_planet = game_state.planets[dest_id]
                    
                    if src_planet.owner == self.player and src_planet.n_ships is not None and src_planet.n_ships > 1:
                        if dest_planet.owner == self.player and enemy_p.get(dest_id, 0.0) > 0:
                            mask[action_idx] = 0.0
                            has_candidates = True

        if not has_candidates:
            return self._heuristic_defense_fallback(game_state, enemy_p, min_enemy_eta)

        masked_q = q_values + mask
        best_action_idx = torch.argmax(masked_q).item()
        
        if masked_q[best_action_idx] == float('-inf'):
            return self._heuristic_defense_fallback(game_state, enemy_p, min_enemy_eta)

        source_id = best_action_idx // self.num_planets
        dest_id = best_action_idx % self.num_planets
        src_planet = game_state.planets[source_id]

        src_ships = self._safe_n_ships(src_planet.n_ships, src_planet.growth_rate, current_tick)
        ships_to_send = min(enemy_p.get(dest_id, 0.0) + 5.0, src_ships - 5.0)

        if ships_to_send < 1.0:
            return self._heuristic_defense_fallback(game_state, enemy_p, min_enemy_eta)

        return Action(
            player_id=self.player,
            source_planet_id=source_id,
            destination_planet_id=dest_id,
            num_ships=float(ships_to_send)
        )

    def _heuristic_defense_fallback(self, game_state: GameState, enemy_p, min_enemy_eta) -> Action:
        current_tick = getattr(game_state, 'game_tick', 0)
        target_id = -1
        max_pressure = -1.0
        max_growth = -1.0

        for i, p in enumerate(game_state.planets):
            if p.owner == self.player:
                p_press = enemy_p.get(i, 0.0)
                if p_press > max_pressure:
                    max_pressure = p_press
                    max_growth = p.growth_rate
                    target_id = i
                elif p_press == max_pressure and p_press > -1.0:
                    if p.growth_rate > max_growth:
                        max_growth = p.growth_rate
                        target_id = i

        if target_id == -1 or max_pressure == 0.0:
            return Action.do_nothing()

        target_planet = game_state.planets[target_id]
        enemy_eta = min_enemy_eta.get(target_id, float('inf'))

        best_src_id = -1
        max_src_ships = -1.0
        timed_candidates = []

        for i, p in enumerate(game_state.planets):
            if p.owner == self.player and i != target_id:
                p_ships = self._safe_n_ships(p.n_ships, p.growth_rate, current_tick)
                dist = p.position.distance(target_planet.position)
                my_eta = dist / (self.params.transporter_speed if self.params else 2.0)
                if my_eta < enemy_eta:
                    timed_candidates.append((i, p_ships))
                if p_ships > max_src_ships:
                    max_src_ships = p_ships
                    best_src_id = i

        if timed_candidates:
            best_src_id = max(timed_candidates, key=lambda x: x[1])[0]

        if best_src_id == -1:
            return Action.do_nothing()

        src_planet = game_state.planets[best_src_id]
        src_ships = self._safe_n_ships(src_planet.n_ships, src_planet.growth_rate, current_tick)

        ships_to_send = min(max_pressure + 5.0, src_ships - 5.0)

        if ships_to_send < 1.0:
            return Action.do_nothing()

        return Action(
            player_id=self.player,
            source_planet_id=best_src_id,
            destination_planet_id=target_id,
            num_ships=float(ships_to_send)
        )

    def _titans_offense(self, game_state: GameState) -> Action:
        current_tick = getattr(game_state, 'game_tick', 0)
        candidates = []

        for src_id, src_planet in enumerate(game_state.planets):
            if src_planet.owner != self.player or src_planet.n_ships is None or src_planet.n_ships <= 1:
                continue
            
            src_ships = self._safe_n_ships(src_planet.n_ships, src_planet.growth_rate, current_tick)

            for dest_id, dest_planet in enumerate(game_state.planets):
                if dest_planet.owner == self.player or src_id == dest_id:
                    continue

                dest_ships = self._safe_n_ships(dest_planet.n_ships, dest_planet.growth_rate, current_tick)

                if not self._is_attack_viable(src_planet, dest_planet, src_ships, dest_ships):
                    continue

                distance = src_planet.position.distance(dest_planet.position)
                eta = distance / self.params.transporter_speed if self.params else (distance / 2.0)

                if dest_planet.owner == Player.Neutral:
                    payload = (dest_ships * 1.1) + 1.0
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

        best_candidate_score = -float('inf')
        best_candidate_action = None

        for candidate_action in candidates:
            cloned_state = game_state.model_copy(deep=True)
            fm = ForwardModel(cloned_state, self.params)
            
            fm.step({self.player: candidate_action, self.player.opponent(): self.opp_agent.get_action(fm.state)})
            
            # Fixed Issue 1: Keep evaluating the state space instead of freezing into do_nothing
            for _ in range(self.horizon_ticks - 1):
                if fm.is_terminal():
                    break
                fm.step({self.player: self._get_simulation_action(fm.state), self.player.opponent(): self.opp_agent.get_action(fm.state)})

            if fm.is_terminal():
                leader = fm.get_leader()
                if leader == self.player:
                    score = 999.0
                elif leader == self.player.opponent():
                    score = -999.0
                else:
                    score = 0.0
            else:
                sim_tick = fm.state.game_tick
                my_total_ships = sum(self._safe_n_ships(p.n_ships, p.growth_rate, sim_tick) for p in fm.state.planets if p.owner == self.player)
                opp_total_ships = sum(self._safe_n_ships(p.n_ships, p.growth_rate, sim_tick) for p in fm.state.planets if p.owner == self.player.opponent())
                my_total_growth = sum(p.growth_rate for p in fm.state.planets if p.owner == self.player)
                opp_total_growth = sum(p.growth_rate for p in fm.state.planets if p.owner == self.player.opponent())
                
                score = (my_total_ships - opp_total_ships) + 10.0 * (my_total_growth - opp_total_growth)

            if score > best_candidate_score:
                best_candidate_score = score
                best_candidate_action = candidate_action

        if best_candidate_action is not None:
            return best_candidate_action

        return Action.do_nothing()

    def get_agent_type(self) -> str:
        return "DQN_Defense_Agent (DQN Defense / Titans Offense)"