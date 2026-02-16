package games.planetwars.runners

import competition_entry.GreedyHeuristicAgent
import games.planetwars.agents.PlanetWarsAgent
import games.planetwars.agents.RemoteAgent
import games.planetwars.agents.evo.SimpleEvoAgent
import games.planetwars.agents.random.BetterRandomAgent
import games.planetwars.agents.random.CarefulRandomAgent
import games.planetwars.core.GameParams
import json_rmi.SimpleAgent
import java.io.File


fun waitForAgentType(
    remoteAgent: RemoteAgent,
    maxRetries: Int = 10,
    initialDelayMs: Double = 200.0,
): String {
    var delay = initialDelayMs
    repeat(maxRetries) { attempt ->
        try {
            val agentName = remoteAgent.getAgentType()
            println("✅ Connected to remote agent: $agentName")
            return agentName
        } catch (e: Exception) {
            println("⏳ Attempt ${attempt + 1} failed: ${e.message}")
            Thread.sleep(delay.toLong())
            delay = (delay * 1.5).coerceAtMost(2000.0)  // exponential backoff up to 2s
        }
    }
    throw RuntimeException("❌ Failed to connect to remote agent after $maxRetries attempts.")
}

fun main(args: Array<String>) {
    if (args.isEmpty()) {
        println("❌ Please provide the port number for the remote agent.")
        return
    }

    val remotePort = args[0].toIntOrNull()
    if (remotePort == null) {
        println("❌ Invalid port number: ${args[0]}")
        return
    }

    val timeout = 40L // milliseconds before each remote call times out - adjust as needed

    // number of games to play between each pair of agents -
    // higher values give more accurate results, at the cost of time
    val gamesPerPair = 5

    val gameParams = GameParams(numPlanets = 20, maxTicks = 2000)
    val baselineAgents = SamplePlayerLists().getRandomTrio()
    baselineAgents.clear()
    baselineAgents.add(BetterRandomAgent())
    baselineAgents.add(CarefulRandomAgent())
    baselineAgents.add(GreedyHeuristicAgent())
//    baselineAgents.add(SimpleEvoAgent())
    val remoteAgent = RemoteAgent("<unused - name retrieved from remoteAgent>", port = remotePort)
    val testAgentName = waitForAgentType(remoteAgent)
    val results = mutableListOf<Triple<String, Double, Int>>()
    val timeResults = mutableListOf<Triple<String, Double, Int>>()

    for (baseline in baselineAgents) {
        println("Running $testAgentName against sample: ${baseline.getAgentType()}... ")
        val league = RoundRobinLeague(
            agents = listOf(remoteAgent, baseline),
            gameParams = gameParams,
            gamesPerPair = gamesPerPair,
            runRemoteAgents = true,
            timeout = timeout,
        )

        val scores = league.runRoundRobin()
        val testEntry = scores[testAgentName]
        if (testEntry != null) {
            results.add(Triple(baseline.getAgentType(), testEntry.winRate(), testEntry.nGames))
            timeResults.add(Triple(baseline.getAgentType(), testEntry.avgActionTime, testEntry.timeoutCount))
        }
    }

    val totalPoints = results.sumOf { it.second * it.third / 100.0 }
    val totalGames = results.sumOf { it.third }
    val avgWinRate = if (totalGames > 0) (100 * totalPoints / totalGames) else 0.0
    val avgActionTime = if (totalGames > 0) timeResults.sumOf { it.second * it.third } / totalGames else 0.0
    val totalTimeouts = timeResults.sumOf { it.third }



    val markdown = buildString {
        append("### $testAgentName Evaluation\n\n")
        append("| Opponent | Win Rate % | Games Played |\n")
        append("|----------|------------|---------------|\n")
        for ((opponent, winRate, games) in results) {
            append("| $opponent | ${"%.1f".format(winRate)} | $games |\n")
        }
        append("| **Overall Average** | **${"%.1f".format(avgWinRate)}** | **$totalGames** |\n\n")
        append("AVG=${"%.1f".format(avgWinRate)}\n")
        append("Average Action Time: ${"%.2f".format(avgActionTime)} ms\n\n")
        append("Total Timeouts: $totalTimeouts\n")
    }

    val outputDir = File("results/sample")
    outputDir.mkdirs()
    val outputFile = File(outputDir, "league.md")
    outputFile.writeText(markdown)

    println(markdown)
}
