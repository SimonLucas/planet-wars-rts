import json

from agents.random_agents import CarefulRandomAgent, PureRandomAgent
from core.forward_model import ForwardModel
from core.game_runner import GameRunner
from core.game_state import GameParams

if __name__ == "__main__":

    game_params = GameParams(num_planets=10)
    agent1 = CarefulRandomAgent()
    agent2 = PureRandomAgent()
    runner = GameRunner(agent2, agent2, game_params)

    state_list = []

    while not runner.forward_model.is_terminal():
        runner.step_game()
        state_list.append(runner.forward_model.state.model_copy(deep=True))

    print(f"Game ended with state: {runner.forward_model.state}")
    print(f"n_states: {len(state_list)}")
    # use pympler to estimate size of game states
    from pympler import asizeof
    # state_list_size = sum(len(s.to_json()) for s in state_list)
    state_list_size = asizeof.asizeof(state_list)
    print(f"Total size of game states: {state_list_size:,} bytes")

    # Convert to actual JSON string (which you'd store or serve)
    json_str = json.dumps([gs.model_dump() for gs in state_list])

    # Get size in bytes of encoded string
    json_bytes = json_str.encode('utf-8')
    print(f"Actual JSON string size: {len(json_bytes):,} bytes")

    # Optional: also see gzipped size
    import gzip

    gzipped = gzip.compress(json_bytes)
    print(f"Gzipped JSON size: {len(gzipped):,} bytes")


    # # now JSON size
    # json_obj = [gs.model_dump() for gs in state_list]
    # json_size = asizeof.asizeof(json_obj)
    # print(f"Total size of JSON representation: {json_size:,} bytes")
    #
    # import gzip
    #
    # compressed = gzip.compress(json_str.encode("utf-8"))
    # print(f"Gzipped JSON size: {len(compressed):,} bytes")
