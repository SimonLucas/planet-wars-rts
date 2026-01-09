package games.planetwars.runners

import games.planetwars.agents.UnifiedPlanetWarsAgent
import games.planetwars.agents.asUnified
import games.planetwars.agents.random.BetterRandomAgent
import games.planetwars.agents.random.PureRandomAgent
import games.planetwars.core.*

/**
 * Game runner that works with the unified agent interface, supporting both fully and
 * partially observable game modes with a single interface.
 *
 * This runner can execute games in either:
 * - Fully observable mode: Agents receive observations with complete information (no nulls)
 * - Partially observable mode: Agents receive observations with hidden information (nulls for opponent data)
 *
 * @param agent1 The first unified agent
 * @param agent2 The second unified agent
 * @param gameParams Game parameters
 * @param partialObservability If true, runs in partially observable mode; if false, fully observable mode
 *
 * Example usage:
 * ```
 * // Wrap existing agents
 * val agent1 = BetterRandomAgent().asUnified()
 * val agent2 = GreedyHeuristicAgent().asUnified()
 *
 * // Run in fully observable mode
 * val runner1 = UnifiedGameRunner(agent1, agent2, gameParams, partialObservability = false)
 * runner1.runGame()
 *
 * // Run in partially observable mode
 * val runner2 = UnifiedGameRunner(agent1, agent2, gameParams, partialObservability = true)
 * runner2.runGame()
 * ```
 */
data class UnifiedGameRunner(
    val agent1: UnifiedPlanetWarsAgent,
    val agent2: UnifiedPlanetWarsAgent,
    val gameParams: GameParams,
    val partialObservability: Boolean = false
) {
    var gameState: GameState = GameStateFactory(gameParams).createGame()
    var forwardModel: ForwardModel = ForwardModel(gameState.deepCopy(), gameParams)

    init {
        newGame()
    }

    /**
     * Run a complete game from start to finish
     */
    fun runGame(): ForwardModel {
        newGame()
        while (!forwardModel.isTerminal()) {
            val gameState = forwardModel.state

            // Create observations based on observability mode
            val (p1Observation, p2Observation) = if (partialObservability) {
                // Partially observable: each player sees only their own information
                Pair(
                    ObservationFactory.create(gameState, setOf(Player.Player1)),
                    ObservationFactory.create(gameState, setOf(Player.Player2))
                )
            } else {
                // Fully observable: both players see everything (including neutral planets)
                Pair(
                    ObservationFactory.create(gameState, setOf(Player.Player1, Player.Player2, Player.Neutral)),
                    ObservationFactory.create(gameState, setOf(Player.Player1, Player.Player2, Player.Neutral))
                )
            }

            val actions = mapOf(
                Player.Player1 to agent1.getAction(p1Observation),
                Player.Player2 to agent2.getAction(p2Observation),
            )
            forwardModel.step(actions)
        }

        // Notify agents that the game is over
        agent1.processGameOver(forwardModel.state)
        agent2.processGameOver(forwardModel.state)

        return forwardModel
    }

    /**
     * Initialize or reset the game
     */
    fun newGame() {
        if (gameParams.newMapEachRun) {
            gameState = GameStateFactory(gameParams).createGame()
        }
        forwardModel = ForwardModel(gameState.deepCopy(), gameParams)
        agent1.prepareToPlayAs(Player.Player1, gameParams)
        agent2.prepareToPlayAs(Player.Player2, gameParams)
    }

    /**
     * Step the game forward by one tick
     */
    fun stepGame(): ForwardModel {
        if (forwardModel.isTerminal()) {
            return forwardModel
        }

        val gameState = forwardModel.state

        // Create observations based on observability mode
        val (p1Observation, p2Observation) = if (partialObservability) {
            Pair(
                ObservationFactory.create(gameState, setOf(Player.Player1)),
                ObservationFactory.create(gameState, setOf(Player.Player2))
            )
        } else {
            Pair(
                ObservationFactory.create(gameState, setOf(Player.Player1, Player.Player2, Player.Neutral)),
                ObservationFactory.create(gameState, setOf(Player.Player1, Player.Player2, Player.Neutral))
            )
        }

        val actions = mapOf(
            Player.Player1 to agent1.getAction(p1Observation),
            Player.Player2 to agent2.getAction(p2Observation),
        )
        forwardModel.step(actions)
        return forwardModel
    }

    /**
     * Run multiple games and return the results
     */
    fun runGames(nGames: Int): Map<Player, Int> {
        val scores = mutableMapOf(Player.Player1 to 0, Player.Player2 to 0, Player.Neutral to 0)
        for (i in 0 until nGames) {
            val finalModel = runGame()
            val winner = finalModel.getLeader()
            scores[winner] = scores[winner]!! + 1
        }
        return scores
    }
}

fun main() {
    val gameParams = GameParams(numPlanets = 20)
    val nGames = 100  // Number of games for performance test

    // Wrap existing agents using the unified interface
    val agent1 = PureRandomAgent().asUnified()
    val agent2 = BetterRandomAgent().asUnified()

    println("=== Testing Fully Observable Mode ===")
    val fullyObservableRunner = UnifiedGameRunner(agent1, agent2, gameParams, partialObservability = false)
    val fullyObservableResult = fullyObservableRunner.runGame()
    println("Game over!")
    println(fullyObservableResult.statusString())

    println("\n=== Testing Partially Observable Mode ===")
    val partiallyObservableRunner = UnifiedGameRunner(agent1, agent2, gameParams, partialObservability = true)
    val partiallyObservableResult = partiallyObservableRunner.runGame()
    println("Game over!")
    println(partiallyObservableResult.statusString())

    println("\n=== Running Performance Test ($nGames games each) ===")

    // Test fully observable
    val t1 = System.currentTimeMillis()
    val fullyObservableScores = fullyObservableRunner.runGames(nGames)
    val dt1 = System.currentTimeMillis() - t1
    println("\nFully Observable Results ($nGames games):")
    println(fullyObservableScores)
    println("Time per game: ${dt1.toDouble() / nGames} ms")

    // Test partially observable
    val t2 = System.currentTimeMillis()
    val partiallyObservableScores = partiallyObservableRunner.runGames(nGames)
    val dt2 = System.currentTimeMillis() - t2
    println("\nPartially Observable Results ($nGames games):")
    println(partiallyObservableScores)
    println("Time per game: ${dt2.toDouble() / nGames} ms")

    println("\nSuccessful actions: ${ForwardModel.nActions}")
    println("Failed actions: ${ForwardModel.nFailedActions}")
}
