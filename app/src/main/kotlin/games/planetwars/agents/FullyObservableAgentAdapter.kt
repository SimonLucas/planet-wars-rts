package games.planetwars.agents

import games.planetwars.core.*

/**
 * Optimized adapter that wraps a fully observable PlanetWarsAgent to work with the unified
 * Observation-based interface.
 *
 * This allows existing agents to participate in both fully and partially observable games
 * without modification. The adapter intelligently detects whether an observation contains
 * hidden information and optimizes accordingly:
 *
 * - In fully observable games: Direct conversion without sampling (zero overhead)
 * - In partially observable games: Uses HiddenInfoSampler to reconstruct missing information
 *
 * @param wrappedAgent The existing PlanetWarsAgent to adapt
 * @param sampler Optional custom sampler for hidden information. If null, uses DefaultHiddenInfoSampler
 *
 * Example usage:
 * ```
 * val greedyAgent = GreedyHeuristicAgent()
 * val unifiedAgent = FullyObservableAgentAdapter(greedyAgent)
 * // Or using extension function:
 * val unifiedAgent2 = greedyAgent.asUnified()
 * ```
 */
class FullyObservableAgentAdapter(
    private val wrappedAgent: PlanetWarsAgent,
    private val sampler: HiddenInfoSampler? = null
) : UnifiedPlanetWarsAgent {

    private lateinit var params: GameParams
    private lateinit var reconstructor: GameStateReconstructor

    override fun getAction(observation: Observation): Action {
        val gameState = if (isFullyObservable(observation)) {
            // No hidden information - directly convert without sampling (zero overhead)
            observationToGameState(observation)
        } else {
            // Has hidden information - use reconstructor with sampling
            reconstructor.reconstruct(observation)
        }

        return wrappedAgent.getAction(gameState)
    }

    override fun getAgentType(): String {
        return wrappedAgent.getAgentType()
    }

    override fun prepareToPlayAs(player: Player, params: GameParams, opponent: String?): String {
        this.params = params
        val effectiveSampler = sampler ?: DefaultHiddenInfoSampler(params)
        this.reconstructor = GameStateReconstructor(effectiveSampler)
        return wrappedAgent.prepareToPlayAs(player, params, opponent)
    }

    override fun processGameOver(finalState: GameState) {
        wrappedAgent.processGameOver(finalState)
    }

    /**
     * Check if observation contains any hidden information (nulls).
     * Returns true if all information is visible (fully observable).
     */
    private fun isFullyObservable(observation: Observation): Boolean {
        return observation.observedPlanets.all { planet ->
            planet.nShips != null &&
            (planet.transporter == null || planet.transporter.nShips != null)
        }
    }

    /**
     * Convert fully observable observation directly to GameState without sampling.
     * This method should only be called when isFullyObservable() returns true.
     */
    private fun observationToGameState(observation: Observation): GameState {
        val planets = observation.observedPlanets.map { observed ->
            Planet(
                owner = observed.owner,
                nShips = observed.nShips!!, // Safe because we checked isFullyObservable
                position = observed.position,
                growthRate = observed.growthRate,
                radius = observed.radius,
                transporter = observed.transporter?.let { trans ->
                    Transporter(
                        s = trans.s,
                        v = trans.v,
                        owner = trans.owner,
                        sourceIndex = trans.sourceIndex,
                        destinationIndex = trans.destinationIndex,
                        nShips = trans.nShips!! // Safe because we checked
                    )
                },
                id = observed.id
            )
        }
        return GameState(planets, observation.gameTick)
    }
}
