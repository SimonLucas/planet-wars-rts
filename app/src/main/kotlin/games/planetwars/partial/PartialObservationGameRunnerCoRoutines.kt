package games.planetwars.partial

import competition_entry.CarefulPartialAgent
import games.planetwars.agents.Action
import games.planetwars.agents.PartialObservationAgent
import games.planetwars.agents.PartialRemoteAgent
import games.planetwars.agents.RemotePartialObservationAgent
import games.planetwars.core.*
import kotlinx.coroutines.*
import kotlin.system.measureTimeMillis

data class PartialObservationGameRunnerCoRoutines(
    val agent1: RemotePartialObservationAgent,
    val agent2: RemotePartialObservationAgent,
    val gameParams: GameParams,
    val timeoutMillis: Long = 500, // Timeout for agent responses
) {
    var gameState: GameState = GameStateFactory(gameParams).createGame()
    var forwardModel: ForwardModel = ForwardModel(gameState.deepCopy(), gameParams)

    // Stores the latest actions from agents, even if computed late
    private var latestAction1: Action = Action.doNothing()
    private var latestAction2: Action = Action.doNothing()

    fun runGame(): ForwardModel {
        if (gameParams.newMapEachRun) {
            gameState = GameStateFactory(gameParams).createGame()
        }
        agent1.prepareToPlayAs(Player.Player1, gameParams, )
        agent2.prepareToPlayAs(Player.Player2, gameParams, )
        forwardModel = ForwardModel(gameState.deepCopy(), gameParams)
        runBlocking {
            while (!forwardModel.isTerminal()) {
                val actions = getTimedActions(forwardModel.state)
                forwardModel.step(actions)
            }
        }
        return forwardModel
    }

    suspend fun getTimedActions(state: GameState): Map<Player, Action> = coroutineScope {
        val doNothingAction = Action.doNothing()

        // Create a supervisor scope to manage child jobs independently
        val job = SupervisorJob()
        val scope = CoroutineScope(coroutineContext + job)

        try {
            val action1 = scope.async(Dispatchers.Default) {
                val obs1 = ObservationFactory.create(gameState, setOf(Player.Player1))
                latestAction1 = agent1.getAction(obs1) // Runs in a background thread
                latestAction1
            }

            val action2 = scope.async(Dispatchers.Default) {
                val obs2 = ObservationFactory.create(gameState, setOf(Player.Player2))
                latestAction1 = agent2.getAction(obs2) // Runs in a background thread
                latestAction2
            }

            // Only wait for timeoutMillis for the agent actions, but do not cancel if they take longer
            val action1Result = withTimeoutOrNull(timeoutMillis) { action1.await() } ?: doNothingAction
            val action2Result = withTimeoutOrNull(timeoutMillis) { action2.await() } ?: doNothingAction

            mapOf(
                Player.Player1 to action1Result,
                Player.Player2 to action2Result
            )
        } finally {
            // Ensure any remaining jobs are cancelled when the game terminates
            job.cancelChildren()
        }
    }

    fun newGame() {
        forwardModel = ForwardModel(gameState.deepCopy(), gameParams)
    }

    fun stepGame(): ForwardModel {
        if (forwardModel.isTerminal()) {
            return forwardModel
        }
        runBlocking {
            val actions = getTimedActions(forwardModel.state)
            forwardModel.step(actions)
        }
        return forwardModel
    }

    fun runGames(nGames: Int): Map<Player, Int> {
        val scores = mutableMapOf(Player.Player1 to 0, Player.Player2 to 0, Player.Neutral to 0)
        val timePerGame = measureTimeMillis {
            runBlocking {
                repeat(nGames) {
                    val finalModel = runGame()
                    val winner = finalModel.getLeader()
                    scores[winner] = scores[winner]!! + 1
                }
            }
        }
        println(forwardModel.statusString())
        println("Time per game: ${timePerGame.toDouble() / nGames} ms")
        return scores
    }
}


fun main() {
    val gameParams = GameParams(numPlanets = 20, maxTicks = 1000)
//    val gameState = GameStateFactory(gameParams).createGame()
    val agent1 = PartialRemoteAgent("<specified by server>", 7080)
    val agent2 = CarefulPartialAgent()
    print("Agent 1 type: ${agent1.getAgentType()}\n")
    print("Agent 2 type: ${agent2.getAgentType()}\n")
    val gameRunner = PartialObservationGameRunnerCoRoutines(agent1, agent2, gameParams)
    val finalModel = gameRunner.runGame()
    println("Game over!")
    println(finalModel.statusString())
    // time to run a bunch of games
    val nGames = 1
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
