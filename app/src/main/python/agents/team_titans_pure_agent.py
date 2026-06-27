# ==================================================
# 📄 agents/team_titans_pure_agent.py
# Exact Implementation of Team Titans Architecture
# Fully Plug-and-Play, Single-File Architecture
# ==================================================
import os
import sys
import math
import time
import numpy as np
from core.game_state import GameState, Action, Player
from core.forward_model import ForwardModel
from agents.planet_wars_agent import PlanetWarsPlayer

class GameStateReconstructor:
    """
    Team Titans State Reconstruction Module for Partial Observability.
    Reconstructs hidden states, tracks unknown planets, and provides
    conservative ship estimations with graduated uncertainty reduction.
    """
    def __init__(self):
        self.last_known_ships = {}

    def reconstruct(self, game_state: GameState, current_tick: int) -> tuple:
        unknown_planets = 0
        reconstructed_planets = []

        for idx, p in enumerate(game_state.planets):
            # Deep clone or property copy to avoid altering raw game engine reference
            p_copy = p.model_copy(deep=True) if hasattr(p, 'model_copy') else p
            
            if p_copy.n_ships is None:
                unknown_planets += 1
                # Graduate uncertainty reduction: trace historical knowledge or infer baseline
                if idx in self.last_known_ships:
                    prev_ships, prev_tick, prev_owner = self.last_known_ships[idx]
                    if prev_owner == p_copy.owner and p_copy.owner != Player.Neutral:
                        # Add projected linear growth based on elapsed time under fog
                        elapsed = current_tick - prev_tick
                        p_copy.n_ships = min(150.0, prev_ships + (p_copy.growth_rate * elapsed))
                    else:
                        p_copy.n_ships = 15.0 if p_copy.owner != Player.Neutral else 10.0
                else:
                    p_copy.n_ships = 20.0 if p_copy.owner != Player.Neutral else 10.0
            else:
                # Cache real data when visible
                self.last_known_ships[idx] = (float(p_copy.n_ships), current_tick, p_copy.owner)
            
            reconstructed_planets.append(p_copy)
            
        return unknown_planets, reconstructed_planets


class TeamTitansPureAgent(PlanetWarsPlayer):

    # Time Constraints: 100ms real-time limit, 90ms internal decision budget
    TIME_LIMIT_MS = 90.0       
    MIN_HORIZON   = 25
    MAX_HORIZON   = 100
    OPT_HORIZON   = 60         # Sweet-spot balance (50-75 ticks)

    # Technical Approach: Multi-factor heuristic weights
    W_GROWTH      = 3.0        # Growth-focused evaluation
    W_DISTANCE    = 2.0        # Distance optimization
    W_EFFICIENCY  = 1.0        # Efficiency calculation
    W_THREAT      = 1.5        # Threat assessment

    def __init__(self):
        super().__init__()
        self.player  = None
        self.params  = None
        self.eta_matrix = None # Precomputed distance matrix optimization
        self._map_ready = False
        self.transporter_speed = 2.0
        
        # Core Module Activation
        self.reconstructor = GameStateReconstructor()

    def prepare_to_play_as(self, player: Player, params, *args, **kwargs) -> None:
        super().prepare_to_play_as(player, params, *args, **kwargs)
        self.player = player
        self.params = params
        self._map_ready = False
        self.eta_matrix = None
        if params:
            self.transporter_speed = getattr(params, 'transporter_speed', 2.0) or 2.0

    def get_agent_type(self) -> str:
        return "TeamTitansPure (Exact Multi-Factor Heuristic + Forward Simulation)"

    def _init_matrix(self, game_state: GameState):
        """Precomputed distance matrix optimization."""
        if self._map_ready and self.eta_matrix is not None:
            return
        n = len(game_state.planets)
        spd = self.transporter_speed if self.transporter_speed > 0.01 else 2.0
        self.eta_matrix = np.zeros((n, n), dtype=np.float32)
        for i, pi in enumerate(game_state.planets):
            for j, pj in enumerate(game_state.planets):
                if i != j:
                    self.eta_matrix[i][j] = pi.position.distance(pj.position) / spd
        self._map_ready = True

    def _eta(self, src_id: int, dst_id: int) -> float:
        if self.eta_matrix is not None and src_id < self.eta_matrix.shape[0]:
            return float(self.eta_matrix[src_id][dst_id])
        return 1.0

    def _evaluate(self, fm_state, u_factor: float) -> float:
        """
        Exact Team Titans Pipeline Evaluation Function.
        Combines the base objective balance with the multi-factor heuristic components.
        """
        my_ships   = opp_ships   = 0.0
        my_growth  = opp_growth  = 0.0
        my_threat  = 0.0
        proximity_score = 0.0
        efficiency_score = 0.0

        # 1. Base Score Metrics
        for idx, p in enumerate(fm_state.planets):
            ships  = float(p.n_ships) if p.n_ships is not None else 0.0
            growth = p.growth_rate

            if p.owner == self.player:
                my_ships  += ships
                my_growth += growth
                
                # Distance Optimization Factor: Reward holding central/connected positions
                for enemy_idx, ep in enumerate(fm_state.planets):
                    if ep.owner == self.player.opponent():
                        proximity_score -= self._eta(idx, enemy_idx)
            elif p.owner == self.player.opponent():
                opp_ships  += ships
                opp_growth += growth

        # 2. Threat Assessment Module (Incoming Transporter Pressure)
        for p_src in fm_state.planets:
            t = getattr(p_src, 'transporter', None)
            if t is None:
                continue
            dest = getattr(t, 'destination_index', None)
            if dest is None or dest >= len(fm_state.planets):
                continue
            
            owner = getattr(t, 'owner', None)
            n_ship = getattr(t, 'n_ships', None)
            ship_count = float(n_ship) if n_ship is not None else 0.0
            dest_planet = fm_state.planets[dest]
            
            if owner == self.player.opponent() and dest_planet.owner == self.player:
                my_threat += ship_count  # Real threat load
            elif owner == self.player and dest_planet.owner == self.player.opponent():
                efficiency_score += ship_count  # Valid ship routing efficiency

        # Primary Pipeline Formula: (myShips - oppShips) + 10 × (myGrowth - oppGrowth)
        base_score = (my_ships - opp_ships) + 10.0 * (my_growth - opp_growth)

        # Multi-Factor Component Integration Matrix
        heuristic_modifier = (
            (self.W_GROWTH * (my_growth - opp_growth)) +
            (self.W_DISTANCE * (proximity_score / max(1, len(fm_state.planets)))) +
            (self.W_EFFICIENCY * efficiency_score) -
            (self.W_THREAT * my_threat)
        )

        # Apply Uncertainty Factor Multiplier natively to the integrated total score
        return (base_score + heuristic_modifier) * u_factor

    def get_action(self, game_state: GameState) -> Action:
        t_start = time.time()

        if getattr(game_state, 'game_tick', 0) == 0:
            self._map_ready = False
        self._init_matrix(game_state)

        current_tick = getattr(game_state, 'game_tick', 0)
        
        # 1. Partial Observability: Reconstruct Hidden State & Assess Uncertainty
        unknown_planets, reconstructed_planets = self.reconstructor.reconstruct(game_state, current_tick)
        
        # Apply strict uncertainty factor: u = max(0.6, 1.0 - 0.1 × unknownPlanets)
        u_factor = max(0.6, 1.0 - 0.1 * unknown_planets)

        # Working state contains reconstructed metrics
        working_state = game_state.model_copy(deep=True)
        working_state.planets = reconstructed_planets

        # 2. Generate Valid Source-Target Candidate Pairs
        candidates = []
        for src_id, src_p in enumerate(working_state.planets):
            if src_p.owner != self.player or src_p.n_ships is None or src_p.n_ships <= 1:
                continue

            for dst_id, dst_p in enumerate(working_state.planets):
                if src_id == dst_id:
                    continue

                # Determine dynamic payload values based on target defensive threshold
                eta = self._eta(src_id, dst_id)
                projected_defense = dst_p.n_ships + (dst_p.growth_rate * eta)
                
                if dst_p.owner == Player.Neutral:
                    payload = dst_p.n_ships + 1.0
                elif dst_p.owner == self.player:
                    payload = src_p.n_ships * 0.40  # Fleet balancing relocation
                else:
                    payload = projected_defense + 5.0  # Decisive offensive surplus

                if payload <= 0 or payload >= src_p.n_ships or (src_p.n_ships - payload) < 2.0:
                    continue

                candidates.append(
                    Action(player_id=self.player,
                           source_planet_id=src_id,
                           destination_planet_id=dst_id,
                           num_ships=float(int(payload)))
                )

        if not candidates:
            return Action.do_nothing()

        # 3. Dynamic Horizon Tuning based on computational candidate load
        n_candidates = len(candidates)
        budget_per = max(self.MIN_HORIZON, int((self.TIME_LIMIT_MS - 10) / max(1, n_candidates)))
        horizon = min(self.MAX_HORIZON, max(self.MIN_HORIZON, budget_per))

        best_action = None
        best_score  = -float('inf')

        # 4. Forward Simulate 25-100 ticks & Select Best Evaluated Action
        for action in candidates:
            # Time-bounded search safety escape to strictly guarantee sub-90ms compliance
            if ((time.time() - t_start) * 1000.0) > (self.TIME_LIMIT_MS - 5.0):
                break

            cloned = working_state.model_copy(deep=True)
            fm = ForwardModel(cloned, self.params)

            # Step initial state action execution (Opponent passive modeling assumption)
            fm.step({self.player: action, self.player.opponent(): Action.do_nothing()})

            # Roll lookahead horizon forward
            for _ in range(horizon - 1):
                if fm.is_terminal():
                    break
                fm.step({self.player: Action.do_nothing(), self.player.opponent(): Action.do_nothing()})

            if fm.is_terminal():
                leader = fm.get_leader()
                score = 99999.0 if leader == self.player else -99999.0
            else:
                score = self._evaluate(fm.state, u_factor)

            if score > best_score:
                best_score  = score
                best_action = action

        return best_action if best_action is not None else Action.do_nothing()