package games.planetwars.agents

import games.planetwars.core.*

class HeavyRandomAgent(val delayMillis: Int) : PlanetWarsPlayer() {
    override fun getAction(gameState: GameState): Action {
        // Simulate intensive computation with a busy loop (e.g., MCTS-like behavior)
        val endTime = System.currentTimeMillis() + delayMillis // Pretend to compute for 500ms
        while (System.currentTimeMillis() < endTime) {
            // Perform a dummy computation
            Math.sqrt(Math.random())
        }
        // Return a valid random action
        val myPlanets = gameState.planets.filter { it.owner == player && it.transporter == null }
        if (myPlanets.isEmpty()) return Action.doNothing()

        val otherPlanets = gameState.planets.filter { it.owner == player.opponent() || it.owner == Player.Neutral }
        if (otherPlanets.isEmpty()) return Action.doNothing()

        val source = myPlanets.random()
        val target = otherPlanets.random()
        return Action(player, source.id, target.id, source.nShips / 2)
    }

    override fun getAgentType(): String = "Heavy Computation Agent"
}
