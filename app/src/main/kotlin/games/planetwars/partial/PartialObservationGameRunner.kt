package games.planetwars.partial

import games.planetwars.agents.PartialObservationAgent
import games.planetwars.agents.random.PartialObservationBetterRandomAgent
import games.planetwars.agents.random.PartialObservationPureRandomAgent
import games.planetwars.core.*

data class PartialObservationGameRunner(
    val agent1: PartialObservationAgent,
    val agent2: PartialObservationAgent,
    val gameParams: GameParams,
) {
    var gameState: GameState = GameStateFactory(gameParams).createGame()
    var forwardModel: ForwardModel = ForwardModel(gameState.deepCopy(), gameParams)
    // call newGame() to reset the game state and agents in the constructor
    init {
        newGame()
    }

    fun runGame() : ForwardModel {
        // runs with a fresh copy of the game state each time

        newGame()
        while (!forwardModel.isTerminal()) {
            val gameState = forwardModel.state
            val p1Observation = ObservationFactory.create(gameState, setOf(Player.Player1))
            val p2Observation = ObservationFactory.create(gameState, setOf(Player.Player2))
            val actions = mapOf(
                Player.Player1 to agent1.getAction(p1Observation),
                Player.Player2 to agent2.getAction(p2Observation),
            )
            forwardModel.step(actions)
        }
        return forwardModel
    }

    fun newGame() {
        if (gameParams.newMapEachRun) {
            gameState = GameStateFactory(gameParams).createGame()
        }
        forwardModel = ForwardModel(gameState.deepCopy(), gameParams)
        agent1.prepareToPlayAs(Player.Player1, gameParams)
        agent2.prepareToPlayAs(Player.Player2, gameParams)
    }

    fun stepGame() : ForwardModel {
        if (forwardModel.isTerminal()) {
            return forwardModel
        }
        val gameState = forwardModel.state
        val p1Observation = ObservationFactory.create(gameState, setOf(Player.Player1))
        val p2Observation = ObservationFactory.create(gameState, setOf(Player.Player2))
        val actions = mapOf(
            Player.Player1 to agent1.getAction(p1Observation),
            Player.Player2 to agent2.getAction(p2Observation),
        )
        forwardModel.step(actions)
        return forwardModel
    }

    fun runGames(nGames: Int) : Map<Player, Int> {
        val scores = mutableMapOf(Player.Player1 to 0, Player.Player2 to 0, Player.Neutral to 0)
        for (i in 0 until nGames) {
            val finalModel = runGame()
            val winner = finalModel.getLeader()
            scores[winner] = scores[winner]!! + 1
        }
        println(forwardModel.statusString())

        return scores
    }
}

fun main() {
    val gameParams = GameParams(numPlanets = 20)
//    val gameState = GameStateFactory(gameParams).createGame()
    val agent1 = PartialObservationPureRandomAgent()
    val agent2 = PartialObservationBetterRandomAgent()
    val gameRunner = PartialObservationGameRunner(agent1, agent2, gameParams)
    val finalModel = gameRunner.runGame()
    println("Game over!")
    println(finalModel.statusString())
    // time to run a bunch of games
    val nGames = 1000
    val t = System.currentTimeMillis()
    val results = gameRunner.runGames(nGames)
    val dt = System.currentTimeMillis() - t
    println(results)
    println("Time per game: ${dt.toDouble() / nGames} ms")
    // also print time per step
    val nSteps = ForwardModel.nUpdates
    println("Time per step: ${dt.toDouble() / nSteps} ms")

    println("Successful actions: ${ForwardModel.nActions}")
    println("Failed actions: ${ForwardModel.nFailedActions}")

}
