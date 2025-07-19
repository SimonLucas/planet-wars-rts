package games.planetwars.agents

import games.planetwars.core.GameParams
import games.planetwars.core.GameState
import games.planetwars.core.Observation
import games.planetwars.core.Player

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
