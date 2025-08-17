package games.planetwars.core

import kotlin.random.Random


object GameParamGenerator {
    fun randomParams(seed: Long? = null): GameParams {
        val rng = seed?.let { Random(it) } ?: Random.Default

        // Choose an even number of planets in [10, 30]
        val rawNumPlanets = rng.nextInt(10, 31)
        val numPlanets = if (rawNumPlanets % 2 == 0) rawNumPlanets else rawNumPlanets + 1
        val initialNeutralRatio = rng.nextDouble(0.25, 0.35)
        val minGrowth = 0.05
        val maxGrowth = 0.2
        val transporterSpeed = rng.nextDouble(2.0, 5.0)

        return GameParams(
            numPlanets = numPlanets,
            initialNeutralRatio = initialNeutralRatio,
            minGrowthRate = minGrowth,
            maxGrowthRate = maxGrowth,
            transporterSpeed = transporterSpeed
        )
    }
}

fun main() {
    for (seed in 1..9) {
        val params = GameParamGenerator.randomParams(seed.toLong())
        println("Generated random game parameters with seed $seed: $params")
        // You can create a game state with these parameters if needed
        val gameState = GameStateFactory(params).createGame()
        println("Created game state: $gameState")
    }
}
