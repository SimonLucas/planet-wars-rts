package json_rmi

import games.planetwars.agents.RemoteAgent
import games.planetwars.agents.random.PureRandomAgent
import games.planetwars.core.GameParams
import games.planetwars.runners.GameRunnerCoRoutines
import java.io.File

class JsonLogger(
    logFilePath: String = "remote_agent_log.jsonl",
    private val ignore: Boolean = true
) {
    private val logFile: File = File(logFilePath)

    init {
        if (!ignore) {
            logFile.parentFile?.mkdirs()
            logFile.writeText("") // clear the file on init
        }
    }

    fun log(direction: String, json: String) {
        if (ignore) return
        val entry = """{"dir":"$direction","json":$json}""" + "\n"
        logFile.appendText(entry)
    }

    fun logSend(json: String) = log("send", json)
    fun logRecv(json: String) = log("recv", json)
}

fun main() {
    val logger = JsonLogger(logFilePath = "log_data/test_log.jsonl", ignore = false)
    val agent1 = RemoteAgent(
        className = "competition_entry.CarefulRandomAgent",
        port = 8080,
        logger = logger)
    val agent2 = PureRandomAgent()
    val gameParams = GameParams(numPlanets = 4, initialNeutralRatio = 0.0, maxTicks = 2)
    val runner = GameRunnerCoRoutines(agent1, agent2, gameParams)
    val forwardModel = runner.runGame()
    println("Game over! Final state: $forwardModel")
}

