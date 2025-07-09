package games.planetwars.runners


import games.planetwars.agents.Action
import games.planetwars.agents.PlanetWarsAgent
import games.planetwars.agents.random.PureRandomAgent
import games.planetwars.agents.random.SlowRandomAgent
import games.planetwars.core.*
import kotlinx.coroutines.*
import kotlin.system.measureTimeMillis

data class GameRunnerCoRoutines(
    val agent1: PlanetWarsAgent,
    val agent2: PlanetWarsAgent,
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
        agent1.prepareToPlayAs(Player.Player1, gameParams)
        agent2.prepareToPlayAs(Player.Player2, gameParams)
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
                latestAction1 = agent1.getAction(state.deepCopy()) // Runs in a background thread
                latestAction1
            }

            val action2 = scope.async(Dispatchers.Default) {
                latestAction2 = agent2.getAction(state.deepCopy()) // Runs in a background thread
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
    val gameParams = GameParams(numPlanets = 20)
    val gameState = GameStateFactory(gameParams).createGame()
    val agent1 = PureRandomAgent()
//    val agent2 = games.planetwars.agents.BetterRandomAgent()
//    val agent2 = SlowRandomAgent(delayMillis = 1000)
    val agent2 = games.planetwars.agents.random.HeavyRandomAgent(delayMillis = 100)
    val gameRunner = GameRunnerCoRoutines(agent1, agent2, gameParams, timeoutMillis = 1)
    val finalModel = gameRunner.runGame()
    println("Game over!")
    println(finalModel.statusString())

    // time to run a bunch of games
    val nGames = 5
    val results = gameRunner.runGames(nGames)
    println(results)
}