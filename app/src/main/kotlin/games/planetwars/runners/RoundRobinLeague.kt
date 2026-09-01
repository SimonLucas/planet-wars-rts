package games.planetwars.runners

import competition_entry.GreedyHeuristicAgent
import games.planetwars.agents.DoNothingAgent
import games.planetwars.agents.PlanetWarsAgent
import games.planetwars.agents.RemoteAgent
import games.planetwars.agents.evo.SimpleEvoAgent
import games.planetwars.agents.random.BetterRandomAgent
import games.planetwars.agents.random.CarefulRandomAgent
import games.planetwars.agents.random.PureRandomAgent
import games.planetwars.core.GameParams
import games.planetwars.core.Player

fun main() {

    val gameParams = GameParams(numPlanets = 20, maxTicks = 2000)

    val agents = SamplePlayerLists().getRandomTrio()

    agents.add(GreedyHeuristicAgent())
    val remoteAgent = RemoteAgent("<specified by remote server>", port = 9003)

//    agents.add(remoteAgent)
//    val agents = SamplePlayerLists().getFullList()
//    agents.add(DoNothingAgent())
    val league = RoundRobinLeague(agents, gameParams = gameParams, gamesPerPair = 100, runRemoteAgents = true)
    val results = league.runRoundRobin()
    // use the League utils to print the results
    println(results)
    val writer = LeagueWriter()
    val leagueResult = LeagueResult(results.values.toList())
    val markdownContent = writer.generateMarkdownTable(leagueResult)
    writer.saveMarkdownToFile(markdownContent)

    // print sorted results directly to console
    val sortedResults = results.toList().sortedByDescending { it.second.points }.toMap()
    for (entry in sortedResults.values) {
        println("${entry.agentName} : ${entry.points} : ${entry.nGames}")
    }
}

class SamplePlayerLists {
    fun getRandomTrio(): MutableList<PlanetWarsAgent> {
        return mutableListOf(
            PureRandomAgent(),
            BetterRandomAgent(),
            CarefulRandomAgent(),
        )
    }

    fun getRandomDuo(): MutableList<PlanetWarsAgent> {
        return mutableListOf(
            PureRandomAgent(),
            CarefulRandomAgent(),
        )
    }

    fun getSamplePlayers(): MutableList<PlanetWarsAgent> {
        return mutableListOf(
            PureRandomAgent(),
            BetterRandomAgent(),
            CarefulRandomAgent(),
        )
    }

    fun getFullList(): MutableList<PlanetWarsAgent> {
        return mutableListOf(
//            PureRandomAgent(),
            BetterRandomAgent(),
            CarefulRandomAgent(),
            SimpleEvoAgent(
                useShiftBuffer = true,
                nEvals = 50,
                sequenceLength = 400,
                opponentModel = DoNothingAgent(),
                probMutation = 0.8,
            ),
        )
    }
}

data class RoundRobinLeague(
    val agents: List<PlanetWarsAgent>,
    val gamesPerPair: Int = 10,
    val gameParams: GameParams = GameParams(numPlanets = 20),
    val runRemoteAgents: Boolean = false, // if true, will run remote agents
    val timeout: Long = 50, // timeout in milliseconds for remote agents
    val failedActionAuditLogger: FailedActionAuditLogger = FailedActionAuditLogger(),
) {
    fun runPair(
        agent1: PlanetWarsAgent,
        agent2: PlanetWarsAgent,
        agent1Name: String,
        agent2Name: String
    ): Triple<Map<Player, Int>, Map<Player, Double>, Map<Player, Int>> {
        val failedActionHandler: (games.planetwars.core.FailedActionEvent) -> Unit = { event ->
            val agentName = if (event.player == Player.Player1) agent1Name else agent2Name
            val opponentName = if (event.player == Player.Player1) agent2Name else agent1Name
            failedActionAuditLogger.log(agentName, opponentName, event)
        }
        if (runRemoteAgents) {
            val gameRunner = GameRunnerCoRoutines(
                agent1, agent2, gameParams, timeoutMillis = timeout,
                failedActionHandler = failedActionHandler
            )
            val scores = gameRunner.runGames(gamesPerPair)
            val avgTimes = gameRunner.getAverageActionTimes()
            val timeouts = gameRunner.getTimeoutCount()
            return Triple(scores, avgTimes, timeouts)
        } else {
            val gameRunner = GameRunner(agent1, agent2, gameParams, failedActionHandler)

            val avgTimes = mapOf(
                Player.Player1 to 0.0,
                Player.Player2 to 0.0,
            )
            val timeouts = mapOf(
                Player.Player1 to 0,
                Player.Player2 to 0,
            )
            return Triple(gameRunner.runGames(gamesPerPair), avgTimes, timeouts)
        }
    }

    fun runRoundRobin(): Map<String, LeagueEntry> {
        val t = System.currentTimeMillis()
        val scores = mutableMapOf<String, LeagueEntry>()
        // Cache agent types once upfront to avoid re-calling getAgentType() after connection resets
        val agentTypes = agents.map { it.getAgentType() }
        for (type in agentTypes) {
            scores[type] = LeagueEntry(type)
        }
        // play each agent against every other agent as Player1 and Player2
        // but not against themselves
        for (i in 0 until agents.size) {
            for (j in 0 until agents.size) {
                if (i == j) {
                    continue
                }
                val t = System.currentTimeMillis()
                val agent1 = agents[i]
                val agent2 = agents[j]
                val type1 = agentTypes[i]
                val type2 = agentTypes[j]
                println("Running $type1 vs $type2... ")
                val result = runPair(agent1, agent2, type1, type2)
                // update the league scores for each agent
                val leagueEntry1 = scores[type1]!!
                val leagueEntry2 = scores[type2]!!
                leagueEntry1.points += result.first[Player.Player1]!!
                leagueEntry2.points += result.first[Player.Player2]!!
                leagueEntry1.avgActionTime += result.second[Player.Player1]!!
                leagueEntry2.avgActionTime += result.second[Player.Player2]!!
                leagueEntry1.timeoutCount += result.third[Player.Player1]!!
                leagueEntry2.timeoutCount += result.third[Player.Player2]!!
                leagueEntry1.nGames += gamesPerPair
                leagueEntry2.nGames += gamesPerPair

                println("$gamesPerPair games took ${(System.currentTimeMillis() - t) / 1000} seconds, ")
            }
        }
        println("Round Robin took ${(System.currentTimeMillis() - t) / 1000} seconds")
        return scores
    }
}
