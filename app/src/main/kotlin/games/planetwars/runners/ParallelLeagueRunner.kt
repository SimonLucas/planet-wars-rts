package games.planetwars.runners
import games.planetwars.agents.random.*
import games.planetwars.agents.evo.SimpleEvoAgent
import games.planetwars.agents.DoNothingAgent
import games.planetwars.core.GameParams
import games.planetwars.agents.PlanetWarsAgent
import kotlinx.coroutines.*

class ParallelLeagueRunner(
    private val leagueConfigs: List<RoundRobinLeague>
) {
    suspend fun runAllLeagues(): Map<String, LeagueEntry> = coroutineScope {
        val results = leagueConfigs.map { league ->
            async(Dispatchers.Default) {
                league.runRoundRobin()
            }
        }.awaitAll()

        return@coroutineScope mergeLeagueResults(results)
    }

    private fun mergeLeagueResults(
        resultList: List<Map<String, LeagueEntry>>
    ): Map<String, LeagueEntry> {
        val merged = mutableMapOf<String, LeagueEntry>()
        for (result in resultList) {
            for ((agentName, entry) in result) {
                val existing = merged.getOrPut(agentName) { LeagueEntry(agentName) }
                existing.points += entry.points
                existing.nGames += entry.nGames
            }
        }
        return merged
    }

    companion object {
        @JvmStatic
        fun main(args: Array<String>) = runBlocking {

            // calc elapsed time
            val startTime = System.currentTimeMillis()

            val gameParams = GameParams(numPlanets = 20, maxTicks = 2000)

            // Define your agents
            fun makeAgents() = mutableListOf<PlanetWarsAgent>(
                PureRandomAgent(),
                BetterRandomAgent(),
                CarefulRandomAgent(),
//                SimpleEvoAgent(
//                    useShiftBuffer = true,
//                    nEvals = 50,
//                    sequenceLength = 200,
//                    opponentModel = DoNothingAgent(),
//                    probMutation = 0.8,
//                )
            )

            val nLeagues = 24
            val leagues = List(nLeagues) {
                RoundRobinLeague(
                    agents = makeAgents(),
                    gamesPerPair = 1000,
                    gameParams = gameParams,
                    runRemoteAgents = false
                )
            }

            val runner = ParallelLeagueRunner(leagues)
            val combinedResults = runner.runAllLeagues()

            val writer = LeagueWriter()
            val markdown = writer.generateMarkdownTable(LeagueResult(combinedResults.values.toList()))
            writer.saveMarkdownToFile(markdown)

            println("Combined results:")
            combinedResults.values.sortedByDescending { it.points }.forEach {
                println("${it.agentName} : ${it.points} : ${it.nGames}")
            }

            // print elapsed time
            val elapsed = System.currentTimeMillis() - startTime
            println("Elapsed time: ${elapsed/1000} seconds")
        }
    }
}
