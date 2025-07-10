package games.planetwars.core

import util.Vec2d
import kotlin.random.Random

class GameStateFactory(val params: GameParams, seed: Long? = null) {

    private val rng: Random = seed?.let { Random(it) } ?: Random.Default

    fun makeRandomPlanet(params: GameParams, owner: Player): Planet {
        // we only use x in the left half of the screen
        val x = (rng.nextDouble() * params.width / 2).toInt()
        val y = (rng.nextDouble() * params.height).toInt()
        val numShips = (rng.nextDouble() * (params.maxInitialShipsPerPlanet - params.minInitialShipsPerPlanet)
                + params.minInitialShipsPerPlanet)
        val growthRate = rng.nextDouble(params.minGrowthRate, params.maxGrowthRate)
        val radius = growthRate * params.growthToRadiusFactor
        return Planet(owner, numShips, Vec2d(x.toDouble(), y.toDouble()), growthRate, radius)
    }

    fun canAdd(planets: List<Planet>, candidate: Planet, radialSeparation: Double): Boolean {
        val edgeSep = params.edgeSeparation
        if (candidate.position.x - edgeSep < candidate.radius ||
            candidate.position.x + edgeSep > params.width / 2 - candidate.radius) {
            return false
        }
        if (candidate.position.y - edgeSep < candidate.radius ||
            candidate.position.y + edgeSep > params.height - candidate.radius) {
            return false
        }
        for (planet in planets) {
            val planetRadius = planet.growthRate * params.growthToRadiusFactor
            if (planet.position.distance(candidate.position) < radialSeparation * (planetRadius + candidate.radius)) {
                return false
            }
        }
        return true
    }

    fun createGame(): GameState {
        val planets = mutableListOf<Planet>()
        val nNeutral = (params.numPlanets * params.initialNeutralRatio).toInt() / 2
        while (planets.size < params.numPlanets / 2) {
            val player = if (planets.size < nNeutral) Player.Neutral else Player.Player1
            val candidate = makeRandomPlanet(params, player)
            if (canAdd(planets, candidate, params.radialSeparation)) {
                planets.add(candidate)
            }
        }

        val reflectedPlanets = mutableListOf<Planet>()
        for (planet in planets) {
            val reflected = planet.copy(
                position = Vec2d(params.width - planet.position.x, params.height - planet.position.y)
            )
            if (planet.owner == Player.Player1) {
                reflected.owner = Player.Player2
            }
            reflectedPlanets.add(reflected)
        }

        planets.addAll(reflectedPlanets)

        for ((i, planet) in planets.withIndex()) {
            planet.id = i
        }

        return GameState(planets)
    }
}

fun main() {
    val params = GameParams()
    val factory1 = GameStateFactory(params, seed = 42L)
    val factory2 = GameStateFactory(params, seed = 42L)
    val game1 = factory1.createGame()
    val game2 = factory2.createGame()

    println("Game 1 planets:")
    game1.planets.forEach { println(it) }

    println("\nGame 2 planets:")
    game2.planets.forEach { println(it) }

    // The outputs should be identical for the same seed

    // now try without a seed, and see if the planets are different (they should be)
    val factory3 = GameStateFactory(params)

    val game3 = factory3.createGame()
    println("\nGame 3 planets (no seed):")
    game3.planets.forEach { println(it) }
}
