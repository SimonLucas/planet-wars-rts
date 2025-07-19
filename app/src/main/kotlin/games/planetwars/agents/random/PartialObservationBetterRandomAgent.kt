package games.planetwars.agents.random

import games.planetwars.agents.Action
import games.planetwars.agents.PartialObservationPlayer
import games.planetwars.agents.PlanetWarsPlayer
import games.planetwars.agents.RemotePartialObservationPlayer
import games.planetwars.core.GameState
import games.planetwars.core.Observation
import games.planetwars.core.Player

class PartialObservationBetterRandomAgent() : PartialObservationPlayer() {
    override fun getAction(observation: Observation): Action {
        // filter the planets that are owned by the player AND have a transporter available
        val myPlanets = observation.observedPlanets.filter { it.owner == player && it.transporter == null }
        if (myPlanets.isEmpty()) {
            return Action.doNothing()
        }
        // now find a random target planet
        val otherPlanets = observation.observedPlanets.filter { it.owner == player.opponent()  || it.owner == Player.Neutral }
        if (otherPlanets.isEmpty()) {
            return Action.doNothing()
        }
        val source = myPlanets.random()
        val target = otherPlanets.random()

        // we should be able to observer the source ships as we own the planet
        // extract the number of ships from the source planet
        val sourceShips = observation.observedPlanets[source.id].nShips
        if (sourceShips == null) {
            return Action.doNothing()
        }
        return Action(player, source.id, target.id, sourceShips / 2)
    }

    override fun getAgentType(): String {
        return "Better Random Agent"
    }
}