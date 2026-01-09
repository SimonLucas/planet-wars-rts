package games.planetwars.agents

import games.planetwars.core.GameParams
import games.planetwars.core.GameState
import games.planetwars.core.Observation
import games.planetwars.core.Player
import games.planetwars.core.HiddenInfoSampler
import games.planetwars.core.DefaultHiddenInfoSampler
import games.planetwars.core.GameStateReconstructor

/*
    * This interface defines the methods that an agent must implement to play the fully observable game
 */

interface PlanetWarsAgent {
    fun getAction(gameState: GameState): Action
    fun getAgentType(): String
    // player can return its description string
    fun prepareToPlayAs(player: Player, params: GameParams, opponent: String? = DEFAULT_OPPONENT): String

    // this is provided as a default implementation, but can be overridden if needed
    fun processGameOver(finalState: GameState) {}

    companion object {
        const val DEFAULT_OPPONENT = "Anon"
    }

}

/*
    * Kotlin only has single code inheritance, so we use an abstract class to provide a default implementation
    * of prepareToPlayAs - this is useful because many agents will need to know which player they are playing as
    * and may need other resets or initializations prior to playing
 */
abstract class PlanetWarsPlayer : PlanetWarsAgent {
    protected var player: Player = Player.Neutral
    protected var params: GameParams = GameParams()

    override fun prepareToPlayAs(player: Player, params: GameParams, opponent: String?): String {
        this.player = player
        this.params = params
        return getAgentType()
    }
}


/*
    * This interface defines the methods that an agent must implement to play the partially observable game
 */

interface PartialObservationAgent {
    fun getAction(observation: Observation): Action
    fun getAgentType(): String
    fun prepareToPlayAs(player: Player, params: GameParams, opponent: Player? = null): PartialObservationAgent

    // this is provided as a default implementation, but can be overridden if needed
    // note that the final state is fully observable, so the agent can use this to learn from the final state
    fun processGameOver(finalState: GameState) {}

}

/*
    * Kotlin only has single code inheritance, so we use an abstract class to provide a default implementation
    * of prepareToPlayAs - this is useful because many agents will need to know which player they are playing as
    * and may need other resets or initializations prior to playing
 */
abstract class PartialObservationPlayer : PartialObservationAgent {
    protected var player: Player = Player.Neutral
    protected var params: GameParams = GameParams()

    override fun prepareToPlayAs(player: Player, params: GameParams, opponent: Player?): PartialObservationAgent {
        this.player = player
        this.params = params
        return this
    }
}

interface RemotePartialObservationAgent {
    fun getAction(observation: Observation): Action
    fun getAgentType(): String
    fun prepareToPlayAs(player: Player, params: GameParams, opponent: String? = DEFAULT_OPPONENT): String

    // this is provided as a default implementation, but can be overridden if needed
    // note that the final state is fully observable, so the agent can use this to learn from the final state
    fun processGameOver(finalState: GameState) {}

    companion object {
        const val DEFAULT_OPPONENT = "PartialAnon"
    }
}

/*
    * Kotlin only has single code inheritance, so we use an abstract class to provide a default implementation
    * of prepareToPlayAs - this is useful because many agents will need to know which player they are playing as
    * and may need other resets or initializations prior to playing
 */
abstract class RemotePartialObservationPlayer : RemotePartialObservationAgent {
    protected var player: Player = Player.Neutral
    protected var params: GameParams = GameParams()

    override fun prepareToPlayAs(player: Player, params: GameParams, opponent: String?): String {
        this.player = player
        this.params = params
        return getAgentType()
    }
}

/*
    * Unified interface that works with both fully and partially observable games.
    * Agents receive Observations instead of GameStates. In fully observable mode,
    * observations contain complete information (no nulls). In partially observable mode,
    * observations contain nulls for hidden information.
    *
    * This interface allows a single agent implementation to participate in both
    * fully and partially observable games without modification.
 */
interface UnifiedPlanetWarsAgent {
    fun getAction(observation: Observation): Action
    fun getAgentType(): String
    fun prepareToPlayAs(player: Player, params: GameParams, opponent: String? = DEFAULT_OPPONENT): String

    // this is provided as a default implementation, but can be overridden if needed
    fun processGameOver(finalState: GameState) {}

    companion object {
        const val DEFAULT_OPPONENT = "Anon"
    }
}

/*
    * Abstract base class for unified agents, provides common functionality
 */
abstract class UnifiedPlanetWarsPlayer : UnifiedPlanetWarsAgent {
    protected var player: Player = Player.Neutral
    protected var params: GameParams = GameParams()

    override fun prepareToPlayAs(player: Player, params: GameParams, opponent: String?): String {
        this.player = player
        this.params = params
        return getAgentType()
    }

    /**
     * Helper method to convert an observation to a GameState using reconstruction.
     * Agents that prefer to work with GameState objects can use this method.
     *
     * @param observation The observation to convert
     * @param sampler Optional custom sampler for hidden information. If null, uses DefaultHiddenInfoSampler
     * @return A reconstructed GameState
     */
    protected fun toGameState(observation: Observation, sampler: HiddenInfoSampler? = null): GameState {
        val effectiveSampler = sampler ?: DefaultHiddenInfoSampler(params)
        return GameStateReconstructor(effectiveSampler).reconstruct(observation)
    }
}

// === Extension Functions for Easy Adapter Usage ===

/**
 * Extension function to easily wrap a PlanetWarsAgent for use with the unified interface.
 *
 * This allows existing fully observable agents to work in both fully and partially
 * observable games without modification.
 *
 * Example:
 * ```
 * val greedyAgent = GreedyHeuristicAgent()
 * val unifiedAgent = greedyAgent.asUnified()
 * ```
 *
 * @param sampler Optional custom sampler for hidden information reconstruction
 * @return A UnifiedPlanetWarsAgent that wraps this agent
 */
fun PlanetWarsAgent.asUnified(sampler: HiddenInfoSampler? = null): UnifiedPlanetWarsAgent {
    return FullyObservableAgentAdapter(this, sampler)
}

/**
 * Extension function for batch wrapping of agents.
 *
 * Example:
 * ```
 * val agents = listOf(BetterRandomAgent(), GreedyHeuristicAgent(), PureRandomAgent())
 * val unifiedAgents = agents.asUnified()
 * ```
 *
 * @param sampler Optional custom sampler for hidden information reconstruction (applied to all agents)
 * @return A list of UnifiedPlanetWarsAgents
 */
fun List<PlanetWarsAgent>.asUnified(sampler: HiddenInfoSampler? = null): List<UnifiedPlanetWarsAgent> {
    return this.map { it.asUnified(sampler) }
}
