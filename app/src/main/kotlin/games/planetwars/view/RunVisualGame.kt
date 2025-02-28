package games.planetwars.view

import games.planetwars.core.GameParams
import games.planetwars.runners.GameRunner
import games.planetwars.core.GameStateFactory
import games.planetwars.core.Player
import xkg.jvm.AppLauncher

class RunVisualGame {
}


fun main() {
    val gameParams = GameParams(numPlanets = 20)
    val gameState = GameStateFactory(gameParams).createGame()
    val agent2 = games.planetwars.agents.BetterRandomAgent(Player.Player2)
    val agent1 = games.planetwars.agents.PureRandomAgent(Player.Player1)
//    val agent1 = games.planetwars.agents.DoNothingAgent()
//    val agent1 = games.planetwars.agents.BetterRandomAgent(Player.Player1)
    val gameRunner = GameRunner(gameState, agent1, agent2, gameParams)

    val title = "${agent1.getAgentType()} : Planet Wars : ${agent2.getAgentType()}"
    AppLauncher(
        preferredWidth = gameParams.width,
        preferredHeight = gameParams.height,
        app = GameView(params = gameParams, gameState = gameState, gameRunner = gameRunner),
        title = title,
        frameRate = 50.0,
    ).launch()
}
