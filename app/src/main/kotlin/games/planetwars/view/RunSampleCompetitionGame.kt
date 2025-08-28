package games.planetwars.view

import competition_entry.GreedyHeuristicAgent
import games.planetwars.agents.RemoteAgent
import games.planetwars.agents.random.CarefulRandomAgent
import games.planetwars.core.GameParams
import games.planetwars.runners.GameRunner
import games.planetwars.core.GameStateFactory
import games.planetwars.core.Player
import xkg.jvm.AppLauncher

fun main() {
    // Note: to run this you need to have a remote agent servers running on the specified ports.
    // for each of the remote agents.
    val gameParams = GameParams(
        numPlanets = 30,
        maxTicks = 2000,
        initialNeutralRatio = 0.45, // 45% of planets are neutral at the start
        transporterSpeed = 5.0,
        growthToRadiusFactor = 400.0,
    )
    val gameState = GameStateFactory(gameParams).createGame()
    val agent1 = CarefulRandomAgent()
    val agent2 = GreedyHeuristicAgent()
    // Use a remote agent that connects to a game agent server running on a specified port
    // Be sure to start the server first
//    val agent1 = RemoteAgent("<specified by remote server>", port = 62304)
//    val agent2 = RemoteAgent("<specified by remote server>", port = 62277)
//    val agent1 = RemoteAgent("<specified by remote server>", port = 9005)
//    val agent2 = RemoteAgent("<specified by remote server>", port = 9006)
    val gameRunner = GameRunner(agent1, agent2, gameParams)

    val title = "${agent1.getAgentType()} : Planet Wars : ${agent2.getAgentType()}"
    AppLauncher(
        preferredWidth = gameParams.width,
        preferredHeight = gameParams.height,
        app = GameView(
            params = gameParams,
            gameState = gameState,
            gameRunner = gameRunner,
            showInfoFor = setOf(
                Player.Player1,
                Player.Player2,
                Player.Neutral,
            ),
        ),
        title = title,
        frameRate = 50.0,
    ).launch()
}
