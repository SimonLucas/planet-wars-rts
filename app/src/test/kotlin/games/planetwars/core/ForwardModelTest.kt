package games.planetwars.core

import games.planetwars.agents.Action
import org.junit.jupiter.api.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull

class ForwardModelTest {

    @Test
    fun `invalid actions are rejected without changing the source planet`() {
        val params = GameParams(minInitialShipsPerPlanet = 10, numPlanets = 2, initialNeutralRatio = 0.0)
        val state = GameStateFactory(params).createGame()
        val failedActions = mutableListOf<FailedActionEvent>()
        val model = ForwardModel(state, params, failedActions::add)
        val source = state.planets.first { it.owner == Player.Player1 }
        val target = state.planets.first { it.owner == Player.Player2 }
        val initialShips = source.nShips

        val invalidActions = listOf(
            Action(Player.Player1, source.id, target.id, -1.0),
            Action(Player.Player1, source.id, target.id, 0.0),
            Action(Player.Player1, source.id, target.id, Double.NaN),
            Action(Player.Player1, source.id, target.id, Double.POSITIVE_INFINITY),
            Action(Player.Player1, -1, target.id, 1.0),
            Action(Player.Player1, state.planets.size, target.id, 1.0),
            Action(Player.Player1, source.id, -1, 1.0),
            Action(Player.Player1, source.id, state.planets.size, 1.0)
        )

        invalidActions.forEach { action ->
            model.applyActions(mapOf(Player.Player1 to action))
            assertEquals(initialShips, source.nShips, "Invalid action changed ship count: $action")
            assertNull(source.transporter, "Invalid action launched a transporter: $action")
        }
        assertEquals(invalidActions.size, failedActions.size)
        assertEquals(
            setOf(
                "non_positive_ship_count",
                "non_finite_ship_count",
                "invalid_source_planet",
                "invalid_destination_planet"
            ),
            failedActions.map { it.reason }.toSet()
        )
    }

    @Test
    fun `finite positive action remains valid`() {
        val params = GameParams(minInitialShipsPerPlanet = 10, numPlanets = 2, initialNeutralRatio = 0.0)
        val state = GameStateFactory(params).createGame()
        val model = ForwardModel(state, params)
        val source = state.planets.first { it.owner == Player.Player1 }
        val target = state.planets.first { it.owner == Player.Player2 }
        val shipsToSend = source.nShips / 2.0
        val initialShips = source.nShips

        model.applyActions(
            mapOf(Player.Player1 to Action(Player.Player1, source.id, target.id, shipsToSend))
        )

        assertEquals(initialShips - shipsToSend, source.nShips)
        assertEquals(shipsToSend, source.transporter?.nShips)
    }

    @Test
    fun `test transporter sends and arrives correctly`() {

        val params = GameParams(minInitialShipsPerPlanet = 10, numPlanets = 2, initialNeutralRatio = 0.0)
        val state = GameStateFactory(params).createGame()
        val model = ForwardModel(state, params)


        val source = state.deepCopy().planets.firstOrNull { it.owner == Player.Player1 && it.nShips >= 10 }
            ?: error("No suitable source planet found for Player1")

        val target = state.deepCopy().planets.firstOrNull { it.owner == Player.Player2 }
            ?: error("No suitable target planet found for Player2")


        val initialSourceShips = source.nShips

        val action = Action(Player.Player1, source.id, target.id, 10.0)
        println("Action: $action")

        val nShips = action.numShips

        // Step 1: send the transporter
        model.step(mapOf(Player.Player1 to action))

        println(state)

        // Check source ships decreased and transporter created
        assertEquals(initialSourceShips - nShips, state.planets[source.id].nShips, 0.1)
        assertNotNull(state.planets[source.id].transporter, "Transporter should have been launched")

        // Step forward until transporter arrives at target
        while (state.planets[source.id].transporter != null) {
            model.step(emptyMap())
        }

        // when the transporter arrives, the target should have received the invading ships
        // and source and target planets should now have the same number
        assertEquals(state.planets[source.id].nShips, state.planets[target.id].nShips, 0.1)

    }
}
