package games.planetwars.core

import json_rmi.RemoteConstructable
import kotlinx.serialization.Serializable

import util.Vec2d

// Data class to represent an Observation
@Serializable
data class Observation(
    val observedPlanets: List<PlanetObservation>,
    val gameTick: Int
) : RemoteConstructable

// Class responsible for creating Observations from GameStates
class ObservationFactory {
    companion object {
        fun create(gameState: GameState, observers: Set<Player>, includeTransporterLocations: Boolean = true): Observation {
            val observedPlanets = gameState.planets.map { planet ->
                when {
                    observers.contains(planet.owner) -> {
                        // Full visibility for owned planets
                        PlanetObservation(
                            owner = planet.owner,
                            nShips = planet.nShips,
                            position = planet.position,
                            growthRate = planet.growthRate,
                            radius = planet.radius,
                            transporter = planet.transporter?.takeIf { it.owner in observers || includeTransporterLocations }
                                ?.let { TransporterObservation(it.s, it.v, it.owner, it.sourceIndex, it.destinationIndex, if (it.owner in observers) it.nShips else null) },
                            id = planet.id,
                        )
                    }
                    else -> {
                        // Limited visibility for unowned planets
                        PlanetObservation(
                            owner = planet.owner,
                            nShips = null,  // Hide number of ships
                            position = planet.position,
                            growthRate = planet.growthRate,
                            radius = planet.radius,
                            transporter = planet.transporter?.takeIf { includeTransporterLocations }
                                ?.let { TransporterObservation(it.s, it.v, it.owner, it.sourceIndex, it.destinationIndex, null) },
                            id = planet.id
                        )
                    }
                }
            }
            return Observation(observedPlanets, gameState.gameTick)
        }
    }
}

@Serializable
data class PlanetObservation(
    val owner: Player,
    val nShips: Double?, // Nullable to indicate hidden information
    val position: Vec2d,
    val growthRate: Double,
    val radius: Double,
    val transporter: TransporterObservation?,
    val id: Int
): RemoteConstructable

@Serializable
data class TransporterObservation(
    val s: Vec2d,
    val v: Vec2d,
    val owner: Player,
    val sourceIndex: Int,
    val destinationIndex: Int,
    val nShips: Double?
): RemoteConstructable

fun main() {
    val planet1 = Planet(
        owner = Player.Player1,
        nShips = 50.0,
        position = Vec2d(100.0, 200.0),
        growthRate = 1.5,
        radius = 20.0,
        transporter = Transporter(
            s = Vec2d(50.0, 50.0),
            v = Vec2d(1.0, 1.0),
            owner = Player.Player1,
            sourceIndex = 0,
            destinationIndex = 1,
            nShips = 10.0
        ),
        id = 1
    )

    val planet2 = Planet(
        owner = Player.Player2,
        nShips = 75.0,
        position = Vec2d(300.0, 400.0),
        growthRate = 2.0,
        radius = 25.0,
        id = 2
    )

    val gameState = GameState(planets = listOf(planet1, planet2), gameTick = 10)

    val observationForPlayer1 = ObservationFactory.create(gameState, setOf(Player.Player1))
    val observationForPlayer2 = ObservationFactory.create(gameState, setOf(Player.Player2), includeTransporterLocations = false)

    println("Observation for Player 1:")
    println(observationForPlayer1)
    println("\nObservation for Player 2:")
    println(observationForPlayer2)
}
