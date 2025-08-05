from typing import Dict, Optional
from core.game_state import GameState, GameParams, Player, Action, Planet, Transporter, Vec2d


class ForwardModel:
    n_updates = 0
    n_failed_actions = 0
    n_actions = 0

    def __init__(self, state: GameState, params: GameParams):
        self.state = state
        self.params = params

    def step(self, actions: Dict[Player, Action]):
        self.apply_actions(actions)
        pending: Dict[int, Dict[Player, float]] = {}
        self.update_transporters(pending)
        self.update_planets(pending)
        ForwardModel.n_updates += 1
        self.state.game_tick += 1

    def apply_actions(self, actions: Dict[Player, Action]):
        for player, action in actions.items():
            if action == Action.DO_NOTHING:
                continue
            source = self.state.planets[action.source_planet_id]
            target = self.state.planets[action.destination_planet_id]
            if source.transporter is None and source.owner == player and source.n_ships >= action.num_ships:
                source.n_ships -= action.num_ships
                direction = (target.position - source.position).normalize()
                velocity = direction * self.params.transporter_speed
                transporter = Transporter(
                    s=source.position,
                    v=velocity,
                    owner=player,
                    source_index=action.source_planet_id,
                    destination_index=action.destination_planet_id,
                    n_ships=action.num_ships
                )
                source.transporter = transporter
                ForwardModel.n_actions += 1
            else:
                ForwardModel.n_failed_actions += 1

    def is_terminal(self) -> bool:
        if self.state.game_tick > self.params.max_ticks:
            return True
        return not any(p.owner == Player.Player1 for p in self.state.planets) or \
               not any(p.owner == Player.Player2 for p in self.state.planets)

    def status_string(self) -> str:
        return (
            f"Game tick: {self.state.game_tick}; "
            f"Player 1: {int(self.get_ships(Player.Player1))}; "
            f"Player 2: {int(self.get_ships(Player.Player2))}; "
            f"Leader: {self.get_leader().value}"
        )

    def get_ships(self, player: Player) -> float:
        return sum(p.n_ships for p in self.state.planets if p.owner == player)

    def get_leader(self) -> Player:
        s1 = self.get_ships(Player.Player1)
        s2 = self.get_ships(Player.Player2)
        if s1 == s2:
            return Player.Neutral
        return Player.Player1 if s1 > s2 else Player.Player2

    def transporter_arrival(self, destination: Planet, transporter: Transporter,
                            pending: Dict[int, Dict[Player, float]]):
        if destination.id not in pending:
            pending[destination.id] = {Player.Player1: 0.0, Player.Player2: 0.0}
        pending[destination.id][transporter.owner] += transporter.n_ships

    def update_transporters(self, pending: Dict[int, Dict[Player, float]]):
        for planet in self.state.planets:
            transporter = planet.transporter
            if transporter:
                destination = self.state.planets[transporter.destination_index]
                if transporter.s.distance(destination.position) < destination.radius:
                    self.transporter_arrival(destination, transporter, pending)
                    planet.transporter = None
                else:
                    transporter.s = transporter.s + transporter.v

    def update_neutral_planet(self, planet: Planet, pending: Optional[Dict[Player, float]]):
        if not pending:
            return
        p1 = pending.get(Player.Player1, 0.0)
        p2 = pending.get(Player.Player2, 0.0)
        net = p1 - p2
        planet.n_ships -= abs(net)
        if planet.n_ships < 0:
            planet.owner = Player.Player1 if net > 0 else Player.Player2
            planet.n_ships = -planet.n_ships

    def update_player_planet(self, planet: Planet, pending: Optional[Dict[Player, float]]):
        planet.n_ships += planet.growth_rate
        if not pending:
            return
        own_incoming = pending.get(planet.owner, 0.0)
        opp_incoming = pending.get(planet.owner.opponent(), 0.0)
        planet.n_ships += own_incoming - opp_incoming
        if planet.n_ships < 0:
            planet.owner = planet.owner.opponent()
            planet.n_ships = -planet.n_ships

    def update_planets(self, pending: Dict[int, Dict[Player, float]]):
        for planet in self.state.planets:
            p_pending = pending.get(planet.id)
            if planet.owner == Player.Neutral:
                self.update_neutral_planet(planet, p_pending)
            else:
                self.update_player_planet(planet, p_pending)


if __name__ == "__main__":
    from core.game_state_factory import GameStateFactory

    params = GameParams()
    state = GameStateFactory(params).create_game()
    model = ForwardModel(state, params)

    for _ in range(1000):
        model.step({})  # simulate empty action dicts

    print(f"Steps: {ForwardModel.n_updates}")
