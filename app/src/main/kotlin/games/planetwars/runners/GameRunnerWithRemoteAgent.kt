package games.planetwars.runners


import competition_entry.GreedyHeuristicAgent
import games.planetwars.agents.Action
import games.planetwars.agents.DoNothingAgent
import games.planetwars.agents.PlanetWarsAgent
import games.planetwars.agents.RemoteAgent
import games.planetwars.agents.random.PureRandomAgent
import games.planetwars.agents.random.SlowRandomAgent
import games.planetwars.core.*
import kotlinx.coroutines.*
import kotlin.system.measureTimeMillis


fun main() {
    val gameParams = GameParams(numPlanets = 20, maxTicks = 2000)
//    val agent1 = DoNothingAgent()
//    val agent1 = PureRandomAgent()
    val agent1 = GreedyHeuristicAgent()
    val agent2 = RemoteAgent("<specified by remote server>", port = 9006)
    val gameRunner = GameRunnerCoRoutines(agent1, agent2, gameParams, timeoutMillis = 10)
    val finalModel = gameRunner.runGame()
    println("Game over!")
    println(finalModel.statusString())

    // time to run a bunch of games
    val nGames = 10
    val results = gameRunner.runGames(nGames)
    println(results)
    print(agent2.getAgentType())
    // try them in the other order

    val gameRunnerSwitched = GameRunnerCoRoutines(agent2, agent1, gameParams, timeoutMillis = 10)
    val finalModelSwitched = gameRunnerSwitched.runGame()
    println("Game over (switched)!")
    println(finalModelSwitched.statusString())
    // time to run a bunch of games
    val resultsSwitched = gameRunnerSwitched.runGames(nGames)
    println(resultsSwitched)

}
