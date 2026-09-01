package games.planetwars.core

import games.planetwars.agents.Action

class ForwardModel(
    val state: GameState,
    val params: GameParams,
    private val failedActionHandler: ((FailedActionEvent) -> Unit)? = null
) {
    // the forward model applies the current set of actions to the current game state
    // and updates the game state in place
    // keep track of the total number of calls to the model across all instances
    companion object {
        var nUpdates = 0
        var nFailedActions = 0
        var nActions = 0
    }

    fun step(actions: Map<Player, Action>) {
        // increment the number of updates
        applyActions(actions)
        // we use a pending map to track the incoming transporters to each planet at each step
        // we then resolve the pending ships at each planet before updating the number of ships
        // this makes a difference when two transporters arrive at the same time on a neutral planet
        val pending = HashMap<Int, MutableMap<Player, Double>>() // pending ships for each planet
        updateTransporters(pending)
        updatePlanets(pending)
        nUpdates += 1
        state.gameTick++
    }

    fun applyActions(actions: Map<Player, Action>) {
        for ((player, action) in actions) {
            // check if it's do nothing
            if (action == Action.DO_NOTHING) {
                continue
            }
            if (action.sourcePlanetId !in state.planets.indices ||
                action.destinationPlanetId !in state.planets.indices ||
                !action.numShips.isFinite() || action.numShips <= 0.0
            ) {
                rejectAction(player, action, when {
                    action.sourcePlanetId !in state.planets.indices -> "invalid_source_planet"
                    action.destinationPlanetId !in state.planets.indices -> "invalid_destination_planet"
                    !action.numShips.isFinite() -> "non_finite_ship_count"
                    else -> "non_positive_ship_count"
                })
                continue
            }
            val source = state.planets[action.sourcePlanetId]
            val target = state.planets[action.destinationPlanetId]
            if (source.transporter == null && source.owner == player && source.nShips >= action.numShips) {
                // launch a transporter
                source.nShips -= action.numShips
                val s = source.position
                val t = target.position
                val v = (t - s).normalize() * params.transporterSpeed
                val transporter =
                    Transporter(s, v, player, action.sourcePlanetId, action.destinationPlanetId, action.numShips)
                source.transporter = transporter
                nActions += 1
            } else {
                rejectAction(player, action, when {
                    source.owner != player -> "source_not_owned"
                    source.transporter != null -> "transporter_already_active"
                    else -> "insufficient_ships"
                })
            }
        }
    }

    private fun rejectAction(player: Player, action: Action, reason: String) {
        nFailedActions += 1
        failedActionHandler?.invoke(FailedActionEvent(state.gameTick, player, action, reason))
    }

    fun isTerminal(): Boolean {
        // the game is terminal we're out of time or one of the players has no planets
        if (state.gameTick > params.maxTicks) {
            return true
        }
        return state.planets.none { it.owner == Player.Player1 } || state.planets.none { it.owner == Player.Player2 }
    }

    fun statusString(): String {
        return "Game tick: ${state.gameTick}; Player 1: ${getShips(Player.Player1).toInt()}; Player 2: ${getShips(Player.Player2).toInt()}; Leader: ${getLeader()}"
    }

    fun getShips(player: Player): Double {
        return state.planets.filter { it.owner == player }.sumOf { it.nShips }
    }

    fun getLeader(): Player {
        val s1 = getShips(Player.Player1)
        val s2 = getShips(Player.Player2)
        if (s1 == s2) {
            return Player.Neutral
        }
        return if (s1 > s2) Player.Player1 else Player.Player2
    }


    fun transporterArrival(
        destination: Planet,
        transporter: Transporter,
        pending: MutableMap<Int, MutableMap<Player, Double>>
    ) {
        // if there is no pending map for the destination, create one, otherwise just update it
        if (pending[destination.id] == null) {
            pending[destination.id] = mutableMapOf(Player.Player1 to 0.0, Player.Player2 to 0.0)
        }
        // update the pending ships for the destination
        pending[destination.id]!![transporter.owner] = pending[destination.id]!![transporter.owner]!! + transporter.nShips
    }

    // apply the actions to the game state
    private fun updateTransporters(pending: MutableMap<Int, MutableMap<Player, Double>>) {
        // for each transit, update its progress and resolve if it has reached its destination
        // TODO: for each destination we should keep a list of incoming ships to resolve conflicts
        // we do this for fair resolution
        for (planet in state.planets) {
            val transporter = planet.transporter
            if (transporter != null) {
                val destinationPlanet = state.planets[transporter.destinationIndex]
                // check whether the transporter has arrived
                if (transporter.s.distance(destinationPlanet.position) < destinationPlanet.radius) {
                    transporterArrival(destinationPlanet, transporter, pending)
                    planet.transporter = null
                } else {
                    // update the position of the transporter
                    transporter.s += transporter.v
                }
            }
        }
    }


    /*
    To update the planets we first find which player has the most incoming ships
    and subtract the number of ships from the other player, leaving only one with a positive balance
    or possibly both with zero balance.  For a neutral planet, we then subtract the number of ships
    incoming, and if positive, make it belong to that player.

     */

    private fun updateNeutralPlanet(planet: Planet, pending: MutableMap<Player, Double>? = null) {
        if (pending == null) {
            return
        }
        val playerOneIncoming = pending[Player.Player1] ?: 0.0
        val playerTwoIncoming = pending[Player.Player2] ?: 0.0
        val incoming = playerOneIncoming - playerTwoIncoming
        // reduce neutral ships by absolute value of incoming
        planet.nShips -= Math.abs(incoming)
        // if the number is negative, we switch ownership to the player with the most incoming based on the sign
        if (planet.nShips < 0) {
            planet.owner = if (incoming > 0) Player.Player1 else Player.Player2
            planet.nShips = -planet.nShips
        }
    }

    private fun updatePlayerPlanet(planet: Planet, pending: MutableMap<Player, Double>? = null) {
        // this is simple:
        planet.nShips += planet.growthRate
        // resolve any pending ships on the planet
        if (pending == null) {
            return
        }
        val ownIncoming = pending[planet.owner] ?: 0.0
        val opponentIncoming = pending[planet.owner.opponent()] ?: 0.0
        planet.nShips += ownIncoming - opponentIncoming
        // we check if it has switched ownership
        if (planet.nShips < 0) {
            planet.owner = planet.owner.opponent()
            planet.nShips = -planet.nShips
        }
    }


    private fun updatePlanets(pending: MutableMap<Int, MutableMap<Player, Double>>) {
        // update the number of ships on each planet
        for (planet in state.planets) {
            // update the number of ships on the planet
            // we treat neutral planets differently
            if (planet.owner == Player.Neutral) {
                updateNeutralPlanet(planet, pending[planet.id])
            } else {
                updatePlayerPlanet(planet, pending[planet.id])
            }
        }
    }
}

fun main() {
    val state = GameStateFactory(GameParams()).createGame()
    val model = ForwardModel(state, GameParams())
    val nSteps = 1000000
    val t = System.currentTimeMillis()
    for (i in 0 until nSteps) {
        val actions = HashMap<Player, Action>()
        model.step(actions)
    }
    val dt = System.currentTimeMillis() - t
    println("Time per step: ${dt.toDouble() / ForwardModel.nUpdates} ms")
}
