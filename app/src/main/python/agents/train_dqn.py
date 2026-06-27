# ==================================================
# 📄 agents/train_dqn.py
# ==================================================
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
python_root = os.path.abspath(os.path.join(current_dir, ".."))
if python_root not in sys.path:
    sys.path.insert(0, python_root)
import random
import math
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from collections import namedtuple, deque
from core.game_state import GameParams, Player, Action
from core.forward_model import ForwardModel
from core.game_state_factory import GameStateFactory
from agents.greedy_heuristic_agent import GreedyHeuristicAgent
from agents.random_agents import CarefulRandomAgent
from agents.dqn_defense_multi_simulation_agent import DQN_Defense_Multi_Simulation_Agent
from agents.dqn_defense_agent import DQN_Defense_Agent
from core.unified_game_runner import UnifiedGameRunner
from agents.fully_observable_agent_adapter import as_unified

# Monkeypatch the network class inside dqn_defense_multi_simulation_agent to fix its forward pass shape mismatch
import agents.dqn_defense_multi_simulation_agent as dqn_defense_mod
for name in dir(dqn_defense_mod):
    obj = getattr(dqn_defense_mod, name)
    if isinstance(obj, type) and issubclass(obj, nn.Module):
        if hasattr(obj, 'layer3') and hasattr(obj, 'value_head'):
            def fixed_forward(self, x):
                h1 = F.relu(self.layer1(x))
                h2 = F.relu(self.layer2(h1))
                h3 = F.relu(self.layer3(h2))
                q_values = self.q_head(h3)
                value = torch.tanh(self.value_head(h3))
                return q_values, value
            obj.forward = fixed_forward

# ==================================================
# 🧠 Embedded DQN Architecture & Q-Learning Agent
# ==================================================
class TitansDQN(nn.Module):
    def __init__(self, n_observations, n_actions):
        super().__init__()
        self.layer1 = nn.Linear(n_observations, 256)
        self.layer2 = nn.Linear(256, 256)
        self.layer3 = nn.Linear(256, 128)
        self.q_head = nn.Linear(128, n_actions)
        self.value_head = nn.Linear(128, 1)

    def forward(self, x):
        h1 = F.relu(self.layer1(x))
        h2 = F.relu(self.layer2(h1))
        h3 = F.relu(self.layer3(h2))  # This correctly transforms from 256 dimensions down to 128
        
        q_values = self.q_head(h3)
        value = torch.tanh(self.value_head(h3))  # Fixed: changed from h2 to h3 so shape matches (128)
        return q_values, value
    
class DQN(nn.Module):
    def __init__(self, n_observations, n_actions):
        super(DQN, self).__init__()
        self.layer1 = nn.Linear(n_observations, 256)
        self.layer2 = nn.Linear(256, 256)
        self.layer3 = nn.Linear(256, 128)
        self.q_head = nn.Linear(128, n_actions)
        self.v_head = nn.Linear(128, 1)

    def forward(self, x):
        h1 = F.relu(self.layer1(x))
        h2 = F.relu(self.layer2(h1))
        h3 = F.relu(self.layer3(h2))
        return self.q_head(h3), torch.tanh(self.v_head(h3))
    
class QLearningAgent:
    def __init__(self, model_path=None):
        self.num_planets = 10
        self.n_observations = self.num_planets * 7
        self.n_actions = self.num_planets * self.num_planets
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.policy_net = DQN(self.n_observations, self.n_actions).to(self.device)
        
        if model_path is None:
            self.model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "production_dqn.pt")
        else:
            self.model_path = model_path
            
        if os.path.exists(self.model_path):
            try:
                self.policy_net.load_state_dict(torch.load(self.model_path, map_location=self.device))
            except Exception:
                pass
                
        self.player = None
        self.game_params = None
        self.opponent_context = None

    def prepare_to_play_as(self, player, game_params, opponent=None):
        self.player = player
        self.game_params = game_params

    def set_opponent_context(self, context):
        self.opponent_context = context

    def get_action(self, game_state):
        current_tick = getattr(game_state, 'game_tick', 0)
        unknown_count = sum(1 for p in game_state.planets if p.n_ships is None)
        
        friendly_p = {i: 0.0 for i in range(self.num_planets)}
        enemy_p = {i: 0.0 for i in range(self.num_planets)}
        
        for p_src in game_state.planets:
            if p_src.transporter is not None:
                dest_id = p_src.transporter.destination_index
                owner = p_src.transporter.owner
                n_ships = p_src.transporter.n_ships
                if n_ships is None:
                    uncertainty_multiplier = min(2.0, 1.0 + 0.1 * float(unknown_count))
                    baseline = 10.0
                    if owner == Player.Neutral or owner == "Neutral":
                        ships = min(150.0, baseline * uncertainty_multiplier)
                    else:
                        ships = min(150.0, (baseline + float(p_src.growth_rate) * float(current_tick)) * uncertainty_multiplier)
                else:
                    ships = float(n_ships)
                    
                if dest_id < self.num_planets:
                    eta = p_src.transporter.s.distance(game_state.planets[dest_id].position) / p_src.transporter.v.mag() if p_src.transporter.v.mag() > 0.01 else 1.0
                    pressure = ships / (eta + 1.0)
                    if owner == self.player:
                        friendly_p[dest_id] += pressure
                    else:
                        enemy_p[dest_id] += pressure

        state_tensor = state_to_tensor_as_player(game_state, self.player, self.game_params, precomputed_pressures=(friendly_p, enemy_p))
        with torch.no_grad():
            q_values, _ = self.policy_net(state_tensor)
            q_values = q_values.squeeze(0)

        mask = torch.full_like(q_values, float('-inf'))
        has_valid = False
        for idx in range(self.n_actions):
            s_id = idx // self.num_planets
            d_id = idx % self.num_planets
            if s_id < len(game_state.planets) and d_id < len(game_state.planets):
                s_planet = game_state.planets[s_id]
                d_planet = game_state.planets[d_id]
                if s_planet.owner == self.player and s_planet.n_ships is not None and s_planet.n_ships > 1 and s_id != d_id:
                    if d_planet.owner == self.player and enemy_p.get(d_id, 0.0) <= 0:
                        continue
                    s_ships = float(s_planet.n_ships)
                    d_ships = float(d_planet.n_ships) if d_planet.n_ships is not None else 10.0
                    
                    is_viable = True
                    if d_planet.owner != self.player:
                        distance = s_planet.position.distance(d_planet.position)
                        transporter_speed = self.game_params.transporter_speed if self.game_params else 1.0
                        eta = distance / transporter_speed
                        estimated_defense = d_ships + d_planet.growth_rate * eta
                        is_viable = s_ships > estimated_defense
                    
                    if is_viable:
                        mask[idx] = 0.0
                        has_valid = True

        if not has_valid:
            return Action.do_nothing()

        act_idx = torch.argmax(q_values + mask).item()
        src_id = act_idx // self.num_planets
        dest_id = act_idx % self.num_planets
        
        sp = game_state.planets[src_id]
        dp = game_state.planets[dest_id]
        sp_ships = float(sp.n_ships)
        dp_ships = float(dp.n_ships) if dp.n_ships is not None else 0.0
        
        if dp.owner == Player.Neutral:
            s_send = (dp_ships * 1.1) + 1.0
        elif dp.owner == self.player:
            s_send = sp_ships * 0.30
        else:
            eta = sp.position.distance(dp.position) / (self.game_params.transporter_speed if self.game_params else 1.0)
            real_defense = dp_ships + dp.growth_rate * eta
            s_send = min(real_defense + 5.0, sp_ships - 5.0)
            
        f_pay = max(1.0, min(float(s_send), float(sp_ships - 1)))
        
        # FIX: Converted positional initialization to keyword arguments to comply with Pydantic BaseModel structure
        return Action(player_id=self.player, source_planet_id=src_id, destination_planet_id=dest_id, num_ships=f_pay)

# ==================================================
# 🔄 Training Utilities & Core Infrastructure
# ==================================================
Transition = namedtuple('Transition', ('state', 'action', 'next_state', 'reward', 'value_target'))

class ReplayMemory(object):
    def __init__(self, capacity):
        self.memory = deque([], maxlen=capacity)

    def push(self, *args):
        self.memory.append(Transition(*args))

    def sample(self, batch_size):
        return random.sample(self.memory, batch_size)

    def __len__(self):
        return len(self.memory)

BATCH_SIZE = 128
GAMMA = 0.99
EPS_START = 0.9
EPS_END = 0.02
TOTAL_EPISODES = 500
EPS_DECAY = 100000
TAU = 0.005
LR = 3e-4
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

agent = QLearningAgent()
policy_net = agent.policy_net
target_net = DQN(agent.n_observations, agent.n_actions).to(device)
target_net.load_state_dict(policy_net.state_dict())
optimizer = optim.AdamW(policy_net.parameters(), lr=LR, amsgrad=True)
memory = ReplayMemory(25000)
steps_done = 0

def _safe_n_ships(n_ships, growth_rate, current_tick, unknown_planet_count=0, owner=None):
    if n_ships is None:
        uncertainty_multiplier = min(2.0, 1.0 + 0.1 * float(unknown_planet_count))
        baseline = 10.0
        if owner == Player.Neutral or owner == "Neutral":
            return min(150.0, baseline * uncertainty_multiplier)
        else:
            return min(150.0, (baseline + float(growth_rate) * float(current_tick)) * uncertainty_multiplier)
    return float(n_ships)

def _unknown_planet_count(game_state):
    return sum(1 for planet in game_state.planets if planet.n_ships is None)

def _is_attack_viable_standalone(src_planet, dest_planet, src_ships, dest_ships, context_player, current_params):
    if dest_planet.owner == context_player:
        return True
    distance = src_planet.position.distance(dest_planet.position)
    transporter_speed = current_params.transporter_speed if current_params else 1.0
    eta = distance / transporter_speed
    estimated_defense = dest_ships + dest_planet.growth_rate * eta
    return src_ships > estimated_defense

def compute_pressures_and_etas_standalone(game_state, context_player, current_params):
    current_tick = getattr(game_state, 'game_tick', 0)
    unknown_planet_count = _unknown_planet_count(game_state)
    incoming_friendly_pressure = {i: 0.0 for i in range(agent.num_planets)}
    incoming_enemy_pressure = {i: 0.0 for i in range(agent.num_planets)}
    min_enemy_eta = {i: float('inf') for i in range(agent.num_planets)}

    for p_src in game_state.planets:
        if p_src.transporter is not None:
            dest_id = p_src.transporter.destination_index
            owner = p_src.transporter.owner
            ships = _safe_n_ships(p_src.transporter.n_ships, p_src.growth_rate, current_tick, unknown_planet_count, owner=owner)
            if dest_id < agent.num_planets:
                dest_planet = game_state.planets[dest_id]
                eta = p_src.transporter.s.distance(dest_planet.position) / p_src.transporter.v.mag() if p_src.transporter.v.mag() > 0.01 else 1.0
                pressure = ships / (eta + 1.0)
                if owner == context_player:
                    incoming_friendly_pressure[dest_id] += pressure
                else:
                    incoming_enemy_pressure[dest_id] += pressure
                    if eta < min_enemy_eta[dest_id]:
                        min_enemy_eta[dest_id] = eta
    return incoming_friendly_pressure, incoming_enemy_pressure, min_enemy_eta

def _execute_defense_fallback_standalone(game_state, context_player, current_params, enemy_p, min_enemy_eta):
    current_tick = getattr(game_state, 'game_tick', 0)
    unknown_planet_count = _unknown_planet_count(game_state)
    target_id = -1
    max_pressure = -1.0
    max_growth = -1.0

    for i, p in enumerate(game_state.planets):
        if p.owner == context_player:
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
        return -1, -1

    target_planet = game_state.planets[target_id]
    enemy_eta = min_enemy_eta.get(target_id, float('inf'))

    best_src_id = -1
    max_src_ships = -1.0
    timed_candidates = []

    for i, p in enumerate(game_state.planets):
        if p.owner == context_player and i != target_id:
            p_ships = _safe_n_ships(p.n_ships, p.growth_rate, current_tick, unknown_planet_count, owner=p.owner)
            dist = p.position.distance(target_planet.position)
            my_eta = dist / (current_params.transporter_speed if current_params else 1.0)
            if my_eta < enemy_eta:
                timed_candidates.append((i, p_ships))
            if p_ships > max_src_ships:
                max_src_ships = p_ships
                best_src_id = i

    if timed_candidates:
        best_src_id = max(timed_candidates, key=lambda x: x[1])[0]

    return best_src_id, target_id

def select_training_action(game_state, eps_threshold, context_player, current_params):
    my_planets = [p for p in game_state.planets if p.owner == context_player and p.n_ships is not None and p.n_ships > 1]
    if not my_planets or len(game_state.planets) > agent.num_planets:
        return -1, -1, None
    
    friendly_p, enemy_p, min_enemy_eta = compute_pressures_and_etas_standalone(game_state, context_player, current_params)
    current_tick = game_state.game_tick
    unknown_planet_count = _unknown_planet_count(game_state)

    if random.random() < eps_threshold:
        valid_pairs = []
        for s_idx, sp in enumerate(game_state.planets):
            if sp.owner == context_player and sp.n_ships is not None and sp.n_ships > 1:
                for d_idx, dp in enumerate(game_state.planets):
                    if s_idx != d_idx:
                        if dp.owner == context_player and enemy_p.get(d_idx, 0.0) <= 0:
                            continue
                        s_ships = _safe_n_ships(sp.n_ships, sp.growth_rate, current_tick, unknown_planet_count, owner=sp.owner)
                        d_ships = _safe_n_ships(dp.n_ships, dp.growth_rate, current_tick, unknown_planet_count, owner=dp.owner)
                        if _is_attack_viable_standalone(sp, dp, s_ships, d_ships, context_player, current_params):
                            valid_pairs.append((s_idx, d_idx))
        if valid_pairs:
            src, dst = random.choice(valid_pairs)
            return src, dst, None
        else:
            src, dst = _execute_defense_fallback_standalone(game_state, context_player, current_params, enemy_p, min_enemy_eta)
            return src, dst, None

    state_tensor = state_to_tensor_as_player(game_state, context_player, current_params, precomputed_pressures=(friendly_p, enemy_p))
    with torch.no_grad():
        q_values, _ = policy_net(state_tensor)
        q_values = q_values.squeeze(0)

    mask = torch.full_like(q_values, float('-inf'))
    has_valid = False
    for idx in range(agent.n_actions):
        s_id = idx // agent.num_planets
        d_id = idx % agent.num_planets
        if s_id < len(game_state.planets) and d_id < len(game_state.planets):
            s_planet = game_state.planets[s_id]
            d_planet = game_state.planets[d_id]
            if s_planet.owner == context_player and s_planet.n_ships is not None and s_planet.n_ships > 1 and s_id != d_id:
                if d_planet.owner == context_player and enemy_p.get(d_id, 0.0) <= 0:
                    continue
                s_ships = _safe_n_ships(s_planet.n_ships, s_planet.growth_rate, current_tick, unknown_planet_count, owner=s_planet.owner)
                d_ships = _safe_n_ships(d_planet.n_ships, d_planet.growth_rate, current_tick, unknown_planet_count, owner=d_planet.owner)
                if _is_attack_viable_standalone(s_planet, d_planet, s_ships, d_ships, context_player, current_params):
                    mask[idx] = 0.0
                    has_valid = True

    if not has_valid:
        src, dst = _execute_defense_fallback_standalone(game_state, context_player, current_params, enemy_p, min_enemy_eta)
        return src, dst, state_tensor

    act_idx = torch.argmax(q_values + mask).item()
    return act_idx // agent.num_planets, act_idx % agent.num_planets, state_tensor

def state_to_tensor_as_player(game_state, player_context, current_params, precomputed_pressures=None):
    state_list = []
    max_x = current_params.width if current_params else 25.0
    max_y = current_params.height if current_params else 25.0
    
    if precomputed_pressures is not None:
        friendly_p, enemy_p = precomputed_pressures
    else:
        friendly_p, enemy_p, _ = compute_pressures_and_etas_standalone(game_state, player_context, current_params)
    current_tick = getattr(game_state, 'game_tick', 0)
    unknown_planet_count = _unknown_planet_count(game_state)

    for i in range(agent.num_planets):
        if i < len(game_state.planets):
            p = game_state.planets[i]
            owner_val = 1.0 if p.owner == player_context else (-1.0 if p.owner == player_context.opponent() else 0.0)
            n_ships_val = _safe_n_ships(p.n_ships, p.growth_rate, current_tick, unknown_planet_count, owner=p.owner)
            state_list.extend([owner_val, n_ships_val / 100.0, p.growth_rate, p.position.x / max_x, p.position.y / max_y, friendly_p[i], enemy_p[i]])
        else:
            state_list.extend([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    return torch.tensor(state_list, dtype=torch.float32, device=device).unsqueeze(0)

def optimize_model():
    if len(memory) < BATCH_SIZE:
        return
    transitions = memory.sample(BATCH_SIZE)
    batch = Transition(*zip(*transitions))
    non_final_mask = torch.tensor(tuple(map(lambda s: s is not None, batch.next_state)), device=device, dtype=torch.bool)
    non_final_next_states = torch.cat([s for s in batch.next_state if s is not None])

    state_batch = torch.cat(batch.state)
    action_batch = torch.cat(batch.action)
    reward_batch = torch.cat(batch.reward)
    value_target_batch = torch.cat(batch.value_target)
    state_action_values, state_predicted_values = policy_net(state_batch)
    state_action_values = state_action_values.gather(1, action_batch)
    next_state_values = torch.zeros(BATCH_SIZE, device=device)
    with torch.no_grad():
        if non_final_next_states.shape[0] > 0:
            target_q, _ = target_net(non_final_next_states)
            next_state_values[non_final_mask] = target_q.max(1)[0]

    expected_state_action_values = (next_state_values * GAMMA) + reward_batch
    criterion_q = nn.SmoothL1Loss()
    q_learning_loss = criterion_q(state_action_values, expected_state_action_values.unsqueeze(1))

    criterion_v = nn.MSELoss()
    value_loss = criterion_v(state_predicted_values.squeeze(-1), value_target_batch)

    total_loss = q_learning_loss + 0.5 * value_loss
    optimizer.zero_grad()
    total_loss.backward()
    torch.nn.utils.clip_grad_value_(policy_net.parameters(), 100)
    optimizer.step()

# ==================================================
# 🚀 Memory Pre-fill and Execution Loop
# ==================================================
print("📥 Pre-filling replay memory with Expert games...")
game_params_expert = GameParams(num_planets=10, max_ticks=200)
factory = GameStateFactory(game_params_expert)
expert_p1 = GreedyHeuristicAgent()
expert_p2 = GreedyHeuristicAgent()
for g_idx in range(40):
    gs = factory.create_game()
    fm = ForwardModel(gs, game_params_expert)
    expert_p1.prepare_to_play_as(Player.Player1, game_params_expert)
    expert_p2.prepare_to_play_as(Player.Player2, game_params_expert)

    local_exp_buffer_p1 = []
    local_exp_buffer_p2 = []

    while not fm.is_terminal():
        friendly_p1, enemy_p1, _ = compute_pressures_and_etas_standalone(fm.state, Player.Player1, game_params_expert)
        friendly_p2, enemy_p2, _ = compute_pressures_and_etas_standalone(fm.state, Player.Player2, game_params_expert)

        s1 = state_to_tensor_as_player(fm.state, Player.Player1, game_params_expert, precomputed_pressures=(friendly_p1, enemy_p1))
        s2 = state_to_tensor_as_player(fm.state, Player.Player2, game_params_expert, precomputed_pressures=(friendly_p2, enemy_p2))
        a1 = expert_p1.get_action(fm.state)
        a2 = expert_p2.get_action(fm.state)

        idx1 = torch.tensor([[0]], device=device, dtype=torch.long)
        if a1.source_planet_id >= 0:
            idx1 = torch.tensor([[a1.source_planet_id * agent.num_planets + a1.destination_planet_id]], device=device, dtype=torch.long)

        idx2 = torch.tensor([[0]], device=device, dtype=torch.long)
        if a2.source_planet_id >= 0:
            idx2 = torch.tensor([[a2.source_planet_id * agent.num_planets + a2.destination_planet_id]], device=device, dtype=torch.long)

        pre_owners = [p.owner for p in fm.state.planets]
        pre_growth = [p.growth_rate for p in fm.state.planets]
        pre_ships = [p.n_ships for p in fm.state.planets]

        fm.step({Player.Player1: a1, Player.Player2: a2})

        friendly_p1, enemy_p1, _ = compute_pressures_and_etas_standalone(fm.state, Player.Player1, game_params_expert)
        friendly_p2, enemy_p2, _ = compute_pressures_and_etas_standalone(fm.state, Player.Player2, game_params_expert)

        ns1 = state_to_tensor_as_player(fm.state, Player.Player1, game_params_expert, precomputed_pressures=(friendly_p1, enemy_p1))
        ns2 = state_to_tensor_as_player(fm.state, Player.Player2, game_params_expert, precomputed_pressures=(friendly_p2, enemy_p2))

        r1_exp = 0.0
        r2_exp = 0.0
        if a1.source_planet_id >= 0:
            d1 = a1.destination_planet_id
            if pre_owners[d1] == Player.Player2 and fm.state.planets[d1].owner == Player.Player1:
                r1_exp += 5.0 + (pre_growth[d1] * 3.0)
            elif pre_owners[d1] == Player.Neutral and fm.state.planets[d1].owner == Player.Player1:
                r1_exp += 3.0 + (pre_growth[d1] * 2.0)
            elif pre_owners[d1] == Player.Player1:
                r1_exp += 6.0 + (pre_growth[d1] * 2.0)

        if a2.source_planet_id >= 0:
            d2 = a2.destination_planet_id
            if pre_owners[d2] == Player.Player1 and fm.state.planets[d2].owner == Player.Player2:
                r2_exp += 5.0 + (pre_growth[d2] * 3.0)
            elif pre_owners[d2] == Player.Neutral and fm.state.planets[d2].owner == Player.Player2:
                r2_exp += 3.0 + (pre_growth[d2] * 2.0)
            elif pre_owners[d2] == Player.Player2:
                r2_exp += 6.0 + (pre_growth[d2] * 2.0)

        local_exp_buffer_p1.append((s1, idx1, ns1, torch.tensor([r1_exp], device=device)))
        local_exp_buffer_p2.append((s2, idx2, ns2, torch.tensor([r2_exp], device=device)))

    leader = fm.get_leader() if hasattr(fm, 'get_leader') else Player.Neutral
    g_target_p1 = 1.0 if leader == Player.Player1 else (-1.0 if leader == Player.Player2 else 0.0)
    g_target_p2 = 1.0 if leader == Player.Player2 else (-1.0 if leader == Player.Player1 else 0.0)

    v_t1 = torch.tensor([g_target_p1], device=device, dtype=torch.float32)
    v_t2 = torch.tensor([g_target_p2], device=device, dtype=torch.float32)

    for s1, idx1, ns1, r_val in local_exp_buffer_p1:
        memory.push(s1, idx1, ns1, r_val, v_t1)
    for s2, idx2, ns2, r_val in local_exp_buffer_p2:
        memory.push(s2, idx2, ns2, r_val, v_t2)
print(f"✅ Replay memory pre-filled. Size: {len(memory)}")

greedy_agent = GreedyHeuristicAgent()
careful_agent = CarefulRandomAgent()
opponents = [careful_agent, greedy_agent]
frozen_agent = None

if os.path.exists(agent.model_path):
    print("❄️ Freezing current production network into rotation...")
    frozen_agent = QLearningAgent(model_path=agent.model_path)
    opponents.append(frozen_agent)
    
game_params_live = GameParams(num_planets=10, max_ticks=500)
live_factory = GameStateFactory(game_params_live)
policy_net.train()
print("🔥 Launching Live Training...")
for episode in range(TOTAL_EPISODES):
    
    roll = random.random()
    if roll < 0.60 and frozen_agent is not None:
        opp = frozen_agent
        agent.set_opponent_context("blended")
    elif roll < 0.80 or (roll < 0.50 and frozen_agent is None):
        opp = greedy_agent
        agent.set_opponent_context("greedy")
    else:
        opp = careful_agent
        agent.set_opponent_context("random")

    is_partial = random.random() < 0.70
    runner = UnifiedGameRunner(as_unified(agent), as_unified(opp), game_params_live, partial_observability=is_partial)
    fm = runner.forward_model

    opp.prepare_to_play_as(Player.Player2, game_params_live)
    agent.prepare_to_play_as(Player.Player1, game_params_live)

    friendly_p1, enemy_p1, _ = compute_pressures_and_etas_standalone(fm.state, Player.Player1, game_params_live)
    friendly_p2, enemy_p2, _ = compute_pressures_and_etas_standalone(fm.state, Player.Player2, game_params_live)

    state_tensor_p1 = state_to_tensor_as_player(fm.state, Player.Player1, game_params_live, precomputed_pressures=(friendly_p1, enemy_p1))
    state_tensor_p2 = state_to_tensor_as_player(fm.state, Player.Player2, game_params_live, precomputed_pressures=(friendly_p2, enemy_p2))

    episode_buffer_p1 = []
    episode_buffer_p2 = []
    last_action_idx_p1 = None
    last_action_idx_p2 = None

    while not fm.is_terminal():
        steps_done += 1
        eps_threshold = EPS_END + (EPS_START - EPS_END) * math.exp(-1. * steps_done / EPS_DECAY)

        src_p1, dst_p1, valid_s1 = select_training_action(fm.state, eps_threshold, Player.Player1, game_params_live)
        act_p2 = opp.get_action(fm.state)

        if valid_s1 is not None: 
            state_tensor_p1 = valid_s1
        else:
            friendly_p1, enemy_p1, _ = compute_pressures_and_etas_standalone(fm.state, Player.Player1, game_params_live)
            state_tensor_p1 = state_to_tensor_as_player(fm.state, Player.Player1, game_params_live, precomputed_pressures=(friendly_p1, enemy_p1))

        friendly_p2, enemy_p2, _ = compute_pressures_and_etas_standalone(fm.state, Player.Player2, game_params_live)
        state_tensor_p2 = state_to_tensor_as_player(fm.state, Player.Player2, game_params_live, precomputed_pressures=(friendly_p2, enemy_p2))

        act_p1 = Action.do_nothing()
        is_mistake_p1 = False
        action_idx_p1 = torch.tensor([[0]], device=device, dtype=torch.long)

        current_tick = fm.state.game_tick
        friendly_p, enemy_p, min_enemy_eta = compute_pressures_and_etas_standalone(fm.state, Player.Player1, game_params_live)
        unknown_planet_count = _unknown_planet_count(fm.state)

        is_fallback_active_p1 = False
        if src_p1 != -1 and dst_p1 != -1:
            sp1 = fm.state.planets[src_p1]
            dp1 = fm.state.planets[dst_p1]
            sp1_ships = _safe_n_ships(sp1.n_ships, sp1.growth_rate, current_tick, unknown_planet_count, owner=sp1.owner)
            dp1_ships = _safe_n_ships(dp1.n_ships, dp1.growth_rate, current_tick, unknown_planet_count, owner=dp1.owner)
            
            if _is_attack_viable_standalone(sp1, dp1, sp1_ships, dp1_ships, Player.Player1, game_params_live):
                if dp1.owner == Player.Neutral:
                    s_send1 = (dp1_ships * 1.1) + 1.0
                elif dp1.owner == Player.Player1:
                    s_send1 = sp1_ships * 0.30
                else:
                    eta1 = sp1.position.distance(dp1.position) / game_params_live.transporter_speed
                    real_defense1 = dp1_ships + dp1.growth_rate * eta1
                    s_send1 = min(real_defense1 + 5.0, sp1_ships - 5.0)
                    if s_send1 <= real_defense1:
                        is_mistake_p1 = True

                if (sp1_ships - s_send1) < 5.0 or s_send1 > sp1_ships:
                    is_mistake_p1 = True

                action_idx_p1 = torch.tensor([[src_p1 * agent.num_planets + dst_p1]], device=device, dtype=torch.long)
                last_action_idx_p1 = action_idx_p1
                if not is_mistake_p1:
                    f_pay1 = max(1.0, min(float(s_send1), float(sp1_ships - 1)))
                    act_p1 = Action(player_id=Player.Player1, source_planet_id=src_p1, destination_planet_id=dst_p1, num_ships=f_pay1)
            else:
                max_p = enemy_p.get(dst_p1, 0.0)
                s_send1 = max_p + 5.0
                s_send1 = min(s_send1, sp1_ships - 5.0)
                action_idx_p1 = torch.tensor([[src_p1 * agent.num_planets + dst_p1]], device=device, dtype=torch.long)
                last_action_idx_p1 = action_idx_p1
                if s_send1 >= 1.0 and sp1_ships > s_send1:
                    act_p1 = Action(player_id=Player.Player1, source_planet_id=src_p1, destination_planet_id=dst_p1, num_ships=float(s_send1))
                    is_fallback_active_p1 = True

        action_idx_p2 = torch.tensor([[0]], device=device, dtype=torch.long)
        if act_p2.source_planet_id >= 0:
            action_idx_p2 = torch.tensor([[act_p2.source_planet_id * agent.num_planets + act_p2.destination_planet_id]], device=device, dtype=torch.long)
            last_action_idx_p2 = action_idx_p2

        if is_mistake_p1 and src_p1 != -1:
            act_p1 = Action.do_nothing()
        
        pre_owners = [p.owner for p in fm.state.planets]
        pre_growth = [p.growth_rate for p in fm.state.planets]
        pre_ships = [p.n_ships for p in fm.state.planets]

        fm.step({Player.Player1: act_p1, Player.Player2: act_p2})

        friendly_p1, enemy_p1, _ = compute_pressures_and_etas_standalone(fm.state, Player.Player1, game_params_live)
        friendly_p2, enemy_p2, _ = compute_pressures_and_etas_standalone(fm.state, Player.Player2, game_params_live)
        reward_tick = fm.state.game_tick
        reward_unknown_planet_count = _unknown_planet_count(fm.state)

        ns1 = state_to_tensor_as_player(fm.state, Player.Player1, game_params_live, precomputed_pressures=(friendly_p1, enemy_p1))
        ns2 = state_to_tensor_as_player(fm.state, Player.Player2, game_params_live, precomputed_pressures=(friendly_p2, enemy_p2))

        r1 = 0.0
        r2 = 0.0

        my_total_ships_p1 = 0.0
        opp_total_ships_p1 = 0.0
        my_total_growth_p1 = 0.0
        opp_total_growth_p1 = 0.0
        my_total_ships_p2 = 0.0
        opp_total_ships_p2 = 0.0
        my_total_growth_p2 = 0.0
        opp_total_growth_p2 = 0.0

        for planet in fm.state.planets:
            planet_ships = _safe_n_ships(planet.n_ships, planet.growth_rate, reward_tick, reward_unknown_planet_count, owner=planet.owner)
            if planet.owner == Player.Player1:
                my_total_ships_p1 += planet_ships
                my_total_growth_p1 += planet.growth_rate
                opp_total_ships_p2 += planet_ships
                opp_total_growth_p2 += planet.growth_rate
            elif planet.owner == Player.Player2:
                opp_total_ships_p1 += planet_ships
                opp_total_growth_p1 += planet.growth_rate
                my_total_ships_p2 += planet_ships
                my_total_growth_p2 += planet.growth_rate

        if is_mistake_p1 and src_p1 != -1:
            r1 = -1.0
        elif src_p1 != -1:
            if pre_owners[dst_p1] == Player.Player2 and fm.state.planets[dst_p1].owner == Player.Player1:
                r1 += 5.0 + (pre_growth[dst_p1] * 3.0)
            elif pre_owners[dst_p1] == Player.Neutral and fm.state.planets[dst_p1].owner == Player.Player1:
                r1 += 3.0 + (pre_growth[dst_p1] * 2.0)
            if pre_ships[dst_p1] is None:
                r1 += 0.5

        if act_p2.source_planet_id >= 0:
            dst_p2 = act_p2.destination_planet_id
            if pre_owners[dst_p2] == Player.Player1 and fm.state.planets[dst_p2].owner == Player.Player2:
                r2 += 5.0 + (pre_growth[dst_p2] * 3.0)
            elif pre_owners[dst_p2] == Player.Neutral and fm.state.planets[dst_p2].owner == Player.Player2:
                r2 += 3.0 + (pre_growth[dst_p2] * 2.0)
            if pre_ships[dst_p2] is None:
                r2 += 0.5

        r1 += 0.01 * ((my_total_ships_p1 - opp_total_ships_p1) + 10.0 * (my_total_growth_p1 - opp_total_growth_p1))
        r2 += 0.01 * ((my_total_ships_p2 - opp_total_ships_p2) + 10.0 * (my_total_growth_p2 - opp_total_growth_p2))

        episode_buffer_p1.append((state_tensor_p1, action_idx_p1, ns1, r1))

        if act_p2.source_planet_id >= 0:
            episode_buffer_p2.append((state_tensor_p2, action_idx_p2, ns2, r2))
        else:
            episode_buffer_p2.append((state_tensor_p2, action_idx_p2, ns2, r2))

        state_tensor_p1 = ns1
        state_tensor_p2 = ns2
        optimize_model()
        ts = target_net.state_dict()
        ps = policy_net.state_dict()
        for key in ps:
            ts[key] = ps[key] * TAU + ts[key] * (1 - TAU)
        target_net.load_state_dict(ts)
        
    leader = fm.get_leader() if hasattr(fm, 'get_leader') else Player.Neutral
    out_p1 = 1.0 if leader == Player.Player1 else (-1.0 if leader == Player.Player2 else 0.0)
    out_p2 = 1.0 if leader == Player.Player2 else (-1.0 if leader == Player.Player1 else 0.0)

    v_t1 = torch.tensor([out_p1], dtype=torch.float32, device=device)
    v_t2 = torch.tensor([out_p2], dtype=torch.float32, device=device)

    for s_t, a_t, ns_t, r_t in episode_buffer_p1:
        memory.push(s_t, a_t, ns_t, torch.tensor([r_t], device=device, dtype=torch.float32), v_t1)
    for s_t, a_t, ns_t, r_t in episode_buffer_p2:
        memory.push(s_t, a_t, ns_t, torch.tensor([r_t], device=device, dtype=torch.float32), v_t2)

    if last_action_idx_p1 is not None:
        final_r1 = 25.0 if out_p1 == 1.0 else (-25.0 if out_p1 == -1.0 else 0.0)
        friendly_p1, enemy_p1, _ = compute_pressures_and_etas_standalone(fm.state, Player.Player1, game_params_live)
        prev_s1 = state_to_tensor_as_player(fm.state, Player.Player1, game_params_live, precomputed_pressures=(friendly_p1, enemy_p1))
        memory.push(prev_s1, last_action_idx_p1, None, torch.tensor([final_r1], device=device, dtype=torch.float32), v_t1)
        optimize_model()

    if last_action_idx_p2 is not None:
        final_r2 = 25.0 if out_p2 == 1.0 else (-25.0 if out_p2 == -1.0 else 0.0)
        friendly_p2, enemy_p2, _ = compute_pressures_and_etas_standalone(fm.state, Player.Player2, game_params_live)
        prev_s2 = state_to_tensor_as_player(fm.state, Player.Player2, game_params_live, precomputed_pressures=(friendly_p2, enemy_p2))
        memory.push(prev_s2, last_action_idx_p2, None, torch.tensor([final_r2], device=device, dtype=torch.float32), v_t2)
        optimize_model()
    if (episode + 1) % 50 == 0:
        print(f"🎮 Episode {episode+1}/{TOTAL_EPISODES} complete. Buffer size: {len(memory)}. Epsilon: {eps_threshold:.3f}")

print("\n🛡️ Training phase complete. Entering competitive Pitting Safeguard Evaluation...")
challenger_path = os.path.join(os.path.dirname(agent.model_path), "planet_wars_challenger.pt")
os.makedirs(os.path.dirname(challenger_path), exist_ok=True)
torch.save(policy_net.state_dict(), challenger_path)

if not os.path.exists(agent.model_path):
    print("🥇 No existing production model discovered. Automatically promoting challenger.")
    torch.save(policy_net.state_dict(), agent.model_path)
else:
    policy_net.eval()
    baseline_agent = DQN_Defense_Multi_Simulation_Agent(model_path=agent.model_path)
    challenger_agent = DQN_Defense_Multi_Simulation_Agent(model_path=challenger_path)
    
    pitting_runner = UnifiedGameRunner(
        as_unified(challenger_agent),
        as_unified(baseline_agent),
        game_params_live,
        partial_observability=True
    )
    
    challenger_wins = 0
    pitting_games = 5
    print(f"⚔️ Evaluating Challenger vs Production Baseline over {pitting_games} matches...")
    
    for game_i in range(pitting_games):
        fm_pit = pitting_runner.run_game()
        if fm_pit.get_leader() == Player.Player1:
            challenger_wins += 1
            
    print(f"📊 Safeguard Competitive Summary: Challenger won {challenger_wins}/{pitting_games} matches.")
    if challenger_wins >= 1:
        print("🏆 Promotion threshold secured (>=1 wins). Replacing production model parameters!")
        torch.save(torch.load(challenger_path, map_location=device), agent.model_path)
    else:
        print("❌ Rejection threshold hit (<1 wins). Preserving old baseline configuration.")
        
    if os.path.exists(challenger_path):
        os.remove(challenger_path)

print(f"🎉 Pipeline process fully complete.")
policy_net.eval()