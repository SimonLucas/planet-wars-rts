package games.planetwars.core

import games.planetwars.agents.Action
import kotlinx.serialization.Serializable

@Serializable
data class FailedActionEvent(
    val gameTick: Int,
    val player: Player,
    val action: Action,
    val reason: String
)
