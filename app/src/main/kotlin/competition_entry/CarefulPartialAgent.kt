package competition_entry

import games.planetwars.agents.Action
import games.planetwars.agents.RemotePartialObservationPlayer
import games.planetwars.core.Observation

class CarefulPartialAgent() : RemotePartialObservationPlayer() {
    override fun getAction(observation: Observation): Action {
        // filter the planets that are owned by the player AND have a transporter available
        val myPlanets = observation.observedPlanets.filter { it.owner == player && it.transporter == null }
        if (myPlanets.isEmpty()) {
            return Action.doNothing()
        }
        // now find a random target planet owned by the opponent
        val opponentPlanets = observation.observedPlanets.filter { it.owner == player.opponent() }
        if (opponentPlanets.isEmpty()) {
            return Action.doNothing()
        }
        val source = myPlanets.random()
        val sourceShips = observation.observedPlanets[source.id].nShips
        if (sourceShips == null || sourceShips < 2) {
            return Action.doNothing() // Not enough ships to send
        }
        val target = opponentPlanets.random()
        return Action(player, source.id,
            target.id, sourceShips/2)
    }

    override fun getAgentType(): String {
        return "Careful Partial Agent"
    }
}
