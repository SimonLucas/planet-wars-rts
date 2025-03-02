package games.planetwars.runners

import games.planetwars.agents.PlanetWarsAgent
import games.planetwars.core.*

data class GameRunner(
    val gameState: GameState,
    val agent1: PlanetWarsAgent,
    val agent2: PlanetWarsAgent,
    val gameParams: GameParams,
) {
    var forwardModel: ForwardModel = ForwardModel(gameState.deepCopy(), gameParams)
    // call newGame() to reset the game state and agents in the constructor
    init {
        newGame()
    }

    fun runGame() : ForwardModel {
        // runs with a fresh copy of the game state each time
//        val forwardModel = ForwardModel(gameState.deepCopy(), gameParams)
        forwardModel = ForwardModel(gameState.deepCopy(), gameParams)
        agent1.prepareToPlayAs(Player.Player1)
        agent2.prepareToPlayAs(Player.Player2)
        while (!forwardModel.isTerminal()) {
            val actions = mapOf(
                Player.Player1 to agent1.getAction(forwardModel.state.deepCopy()),
                Player.Player2 to agent2.getAction(forwardModel.state.deepCopy()),
            )
            forwardModel.step(actions)
        }
        return forwardModel
    }

    fun newGame() {
        forwardModel = ForwardModel(gameState.deepCopy(), gameParams)
        agent1.prepareToPlayAs(Player.Player1)
        agent2.prepareToPlayAs(Player.Player2)
    }

    fun stepGame() : ForwardModel {
        if (forwardModel.isTerminal()) {
            return forwardModel
        }
        val actions = mapOf(
            Player.Player1 to agent1.getAction(forwardModel.state),
            Player.Player2 to agent2.getAction(forwardModel.state),
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
    val gameState = GameStateFactory(gameParams).createGame()
    val agent1 = games.planetwars.agents.PureRandomAgent()
    val agent2 = games.planetwars.agents.BetterRandomAgent()
    val gameRunner = GameRunner(gameState, agent1, agent2, gameParams)
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
}
