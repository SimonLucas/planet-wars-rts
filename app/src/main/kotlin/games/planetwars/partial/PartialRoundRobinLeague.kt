package games.planetwars.partial

import games.planetwars.agents.PartialObservationAgent
import games.planetwars.agents.random.PartialObservationBetterRandomAgent
import games.planetwars.agents.random.PartialObservationPureRandomAgent
import games.planetwars.core.GameParams
import games.planetwars.core.Player
import games.planetwars.runners.LeagueEntry
import kotlin.collections.iterator

// note this version does NOT use co-routines and does not enforce timeouts

data class PartialRoundRobinLeague(
    val agents: List<PartialObservationAgent>,
    val gamesPerPair: Int = 10,
    val gameParams: GameParams = GameParams(numPlanets = 20),
    val timeout: Long = 50, // timeout in milliseconds for remote agents
) {
    fun runPair(agent1: PartialObservationAgent, agent2: PartialObservationAgent): Map<Player, Int> {
        val gameRunner = PartialObservationGameRunner(agent1, agent2, gameParams)
        return gameRunner.runGames(gamesPerPair)
    }

    fun runRoundRobin(): Map<String, LeagueEntry> {
        val t = System.currentTimeMillis()
        val scores = mutableMapOf<String, LeagueEntry>()
        for (agent in agents) {
            // make a new league entry for each agent in a map indexed by agent type
            scores[agent.getAgentType()] = LeagueEntry(agent.getAgentType())
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
                print("Running ${agent1.getAgentType()} vs ${agent2.getAgentType()}... ")
                val result = runPair(agent1, agent2)
                // update the league scores for each agent
                val leagueEntry1 = scores[agent1.getAgentType()]!!
                val leagueEntry2 = scores[agent2.getAgentType()]!!
                leagueEntry1.points += result[Player.Player1]!!
                leagueEntry2.points += result[Player.Player2]!!
                leagueEntry1.nGames += gamesPerPair
                leagueEntry2.nGames += gamesPerPair
                print("$gamesPerPair games took ${(System.currentTimeMillis() - t) / 1000} seconds, ")
            }
        }
        println("Round Robin took ${(System.currentTimeMillis() - t) / 1000} seconds")
        return scores
    }
}

fun main() {
    val gameParams = GameParams(numPlanets = 20, maxTicks = 1000)
    val agents = listOf< PartialObservationAgent>(
        PartialObservationPureRandomAgent(),
        PartialObservationBetterRandomAgent(),
    )

    val league = PartialRoundRobinLeague(agents, gameParams = gameParams, gamesPerPair = 10)
    val results = league.runRoundRobin()

    // Print the results
    for ((agentType, entry) in results) {
        println("$agentType: ${entry.points} points in ${entry.nGames} games")
    }
}
