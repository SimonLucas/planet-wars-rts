package games.planetwars.view

import games.planetwars.agents.RemoteAgent
import games.planetwars.agents.random.CarefulRandomAgent
import games.planetwars.core.GameParams
import games.planetwars.runners.GameRunner
import games.planetwars.core.GameStateFactory
import xkg.jvm.AppLauncher

fun main() {
    val gameParams = GameParams(numPlanets = 20, maxTicks = 1000)
    val gameState = GameStateFactory(gameParams).createGame()
    val agent1 = CarefulRandomAgent()
    // Use a remote agent that connects to a game agent server running on a specified port
    // Be sure to start the server first
    val agent2 = RemoteAgent("<specified by remote server>", port = 8090)
    val gameRunner = GameRunner(agent1, agent2, gameParams)

    val title = "${agent1.getAgentType()} : Planet Wars : ${agent2.getAgentType()}"
    AppLauncher(
        preferredWidth = gameParams.width,
        preferredHeight = gameParams.height,
        app = GameView(params = gameParams, gameState = gameState, gameRunner = gameRunner),
        title = title,
        frameRate = 100.0,
    ).launch()
}
