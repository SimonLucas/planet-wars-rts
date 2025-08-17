package games.planetwars.runners

import games.planetwars.agents.RemoteAgent
import games.planetwars.core.GameParamGenerator
import games.planetwars.core.GameParams
import java.io.File
import kotlin.math.roundToInt

private fun sanitizeFilename(s: String): String =
    s.lowercase()
        .replace(Regex("""[^a-z0-9._-]+"""), "-")
        .replace(Regex("""-{2,}"""), "-")
        .trim('-', '_', '.')


fun main(args: Array<String>) {
    print(args.joinToString(", ", "Arguments: [", "]\n"))
    if (args.isEmpty()) {
        println("Usage: runRemotePairEvaluation --args=PORT_A,PORT_B[,GAMES_PER_PAIR][,TIMEOUT_MS]")
        println("Example: ./gradlew runRemotePairEvaluation --args=5001,5002,10,40")
        return
    }

    // Accept a single CSV arg like "5001,5002,10,40"
    val parts = args[0].split(',').map { it.trim() }
    if (parts.size < 2) {
        println("❌ Need at least two ports: PORT_A,PORT_B[,GAMES_PER_PAIR][,TIMEOUT_MS]")
        return
    }

    val portA = parts[0].toIntOrNull()
    val portB = parts[1].toIntOrNull()
    if (portA == null || portB == null) {
        println("❌ Invalid port(s): ${parts[0]}, ${parts[1]}")
        return
    }

    val gamesPerPair = parts.getOrNull(2)?.toIntOrNull() ?: 10
    val timeoutMs = parts.getOrNull(3)?.toLongOrNull() ?: 50L

//    val params = GameParams(numPlanets = 20, maxTicks = 2000)
    val params = GameParamGenerator.randomParams()

    val agentA = RemoteAgent("<agentA>", port = portA)
    val agentB = RemoteAgent("<agentB>", port = portB)

    val nameA = waitForAgentType(agentA)
    val nameB = waitForAgentType(agentB)

    if (nameA == nameB) {
        println("⚠️ Both ports report the same agent identity: \"$nameA\". Verify containers are configured correctly.")
    }

    println("🎮 Running $nameA (port $portA) vs $nameB (port $portB)")
    val league = RoundRobinLeague(
        agents = listOf(agentA, agentB),
        gameParams = params,
        gamesPerPair = gamesPerPair,
        runRemoteAgents = true,
        timeout = timeoutMs,
    )

    val scores = league.runRoundRobin()

    val scoreA = scores[nameA]
    val scoreB = scores[nameB]
    val winRateA = scoreA?.winRate() ?: 0.0         // percent (0..100)
    val winRateB = scoreB?.winRate() ?: 0.0
    val gamesA = scoreA?.nGames ?: 0
    val gamesB = scoreB?.nGames ?: 0

    // With mirror order runs, these should match; but be defensive:
    val totalGames = maxOf(gamesA, gamesB)

    // If we don’t have explicit wins/draws from the league, derive a best-effort integer
    // wins = round(winRate% * games / 100). Draws = total - winsA - winsB (never negative).
    val winsA = ((winRateA / 100.0) * gamesA).roundToInt()
    val winsB = ((winRateB / 100.0) * gamesB).roundToInt()
    val draws = (totalGames - winsA - winsB).coerceAtLeast(0)

    val markdown = buildString {
        append("### Remote Pair Evaluation\n\n")
        append("| Agent | Port | Win Rate % | Games |\n")
        append("|-------|------|------------|-------|\n")
        append("| $nameA | $portA | ${"%.1f".format(winRateA)} | $gamesA |\n")
        append("| $nameB | $portB | ${"%.1f".format(winRateB)} | $gamesB |\n\n")
        append("_gamesPerPair=$gamesPerPair  totalGames=$totalGames\n\n")
        append("AVG=${"%.1f".format(winRateA)}\n")
        append("AVG_OTHER=${"%.1f".format(winRateB)}\n")
    }

//    val outDir = File("results/sample")
//    outDir.mkdirs()
//    val fileName = "pair_${sanitizeFilename(nameA)}_vs_${sanitizeFilename(nameB)}.md"
//    File(outDir, fileName).writeText(markdown)

    println(markdown)

    // Machine-parsable footer for Python:
    println("AGENT_A=$nameA")
    println("AGENT_B=$nameB")
    println("PORT_A=$portA")
    println("PORT_B=$portB")
    println("WINS_A=$winsA")
    println("WINS_B=$winsB")
    println("DRAWS=$draws")
    println("TOTAL_GAMES=$totalGames")
    println("GPP=$gamesPerPair")
    println("TIMEOUT_MS=$timeoutMs")
}
