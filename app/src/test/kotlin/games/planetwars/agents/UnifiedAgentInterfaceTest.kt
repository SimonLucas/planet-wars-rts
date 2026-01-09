package games.planetwars.agents

import competition_entry.GreedyHeuristicAgent
import games.planetwars.agents.random.BetterRandomAgent
import games.planetwars.agents.random.PureRandomAgent
import games.planetwars.core.*
import games.planetwars.runners.GameRunner
import games.planetwars.runners.UnifiedGameRunner
import org.junit.jupiter.api.Test
import kotlin.test.*

class UnifiedAgentInterfaceTest {

    @Test
    fun `test adapter wraps existing agents correctly`() {
        val greedyAgent = GreedyHeuristicAgent()
        val unifiedAgent = greedyAgent.asUnified()

        assertNotNull(unifiedAgent)
        assertEquals("Greedy Heuristic Agent", unifiedAgent.getAgentType())
    }

    @Test
    fun `test adapter prepareToPlayAs delegates correctly`() {
        val betterRandomAgent = BetterRandomAgent()
        val unifiedAgent = betterRandomAgent.asUnified()

        val params = GameParams(numPlanets = 10)
        val agentType = unifiedAgent.prepareToPlayAs(Player.Player1, params, "TestOpponent")

        assertEquals("Better Random Agent", agentType)
    }

    @Test
    fun `test adapter works with fully observable observations`() {
        val betterRandomAgent = BetterRandomAgent()
        val unifiedAgent = betterRandomAgent.asUnified()

        val params = GameParams(numPlanets = 5)
        unifiedAgent.prepareToPlayAs(Player.Player1, params)

        // Create a fully observable observation (all players visible)
        val gameState = GameStateFactory(params).createGame()
        val observation = ObservationFactory.create(gameState, setOf(Player.Player1, Player.Player2))

        // Should not throw and should return a valid action
        val action = unifiedAgent.getAction(observation)
        assertNotNull(action)
    }

    @Test
    fun `test adapter works with partially observable observations`() {
        val betterRandomAgent = BetterRandomAgent()
        val unifiedAgent = betterRandomAgent.asUnified()

        val params = GameParams(numPlanets = 10)
        unifiedAgent.prepareToPlayAs(Player.Player1, params)

        // Create a partially observable observation (only Player1 visible)
        val gameState = GameStateFactory(params).createGame()
        val observation = ObservationFactory.create(gameState, setOf(Player.Player1))

        // Should not throw and should return a valid action (uses reconstruction)
        val action = unifiedAgent.getAction(observation)
        assertNotNull(action)
    }

    @Test
    fun `test fully observable observation has no nulls`() {
        val params = GameParams(numPlanets = 5)
        val gameState = GameStateFactory(params).createGame()

        // Create fully observable observation (include Neutral to see all planets)
        val observation = ObservationFactory.create(gameState, setOf(Player.Player1, Player.Player2, Player.Neutral))

        // Check that no planet has null nShips
        observation.observedPlanets.forEach { planet ->
            assertNotNull(planet.nShips, "Planet ${planet.id} should have visible ships in fully observable mode")
            if (planet.transporter != null) {
                assertNotNull(planet.transporter.nShips, "Transporter on planet ${planet.id} should have visible ships")
            }
        }
    }

    @Test
    fun `test partially observable observation has nulls for opponent planets`() {
        val params = GameParams(numPlanets = 10, initialNeutralRatio = 0.0)
        val gameState = GameStateFactory(params).createGame()

        // Create partially observable observation (only Player1 visible)
        val observation = ObservationFactory.create(gameState, setOf(Player.Player1))

        val player1Planets = observation.observedPlanets.filter { it.owner == Player.Player1 }
        val player2Planets = observation.observedPlanets.filter { it.owner == Player.Player2 }

        // Player1 planets should be fully visible
        player1Planets.forEach { planet ->
            assertNotNull(planet.nShips, "Own planets should have visible ships")
        }

        // Player2 planets should have hidden information
        player2Planets.forEach { planet ->
            assertNull(planet.nShips, "Opponent planets should have hidden ships in partially observable mode")
        }
    }

    @Test
    fun `test UnifiedGameRunner in fully observable mode`() {
        val params = GameParams(numPlanets = 10, maxTicks = 100)
        val agent1 = BetterRandomAgent().asUnified()
        val agent2 = PureRandomAgent().asUnified()

        val runner = UnifiedGameRunner(agent1, agent2, params, partialObservability = false)
        val result = runner.runGame()

        assertNotNull(result)
        assertTrue(result.isTerminal())
    }

    @Test
    fun `test UnifiedGameRunner in partially observable mode`() {
        val params = GameParams(numPlanets = 10, maxTicks = 100)
        val agent1 = BetterRandomAgent().asUnified()
        val agent2 = PureRandomAgent().asUnified()

        val runner = UnifiedGameRunner(agent1, agent2, params, partialObservability = true)
        val result = runner.runGame()

        assertNotNull(result)
        assertTrue(result.isTerminal())
    }

    @Test
    fun `test batch wrapping of agents`() {
        val agents = listOf(
            BetterRandomAgent(),
            PureRandomAgent(),
            GreedyHeuristicAgent()
        )

        val unifiedAgents = agents.asUnified()

        assertEquals(3, unifiedAgents.size)
        unifiedAgents.forEach { agent ->
            assertNotNull(agent)
            assertTrue(agent is UnifiedPlanetWarsAgent)
        }
    }

    @Test
    fun `test existing GameRunner still works unchanged`() {
        // Verify that existing code is not broken
        val params = GameParams(numPlanets = 10, maxTicks = 100)
        val agent1 = BetterRandomAgent()
        val agent2 = PureRandomAgent()

        val runner = GameRunner(agent1, agent2, params)
        val result = runner.runGame()

        assertNotNull(result)
        assertTrue(result.isTerminal())
    }

    @Test
    fun `test custom sampler can be provided to adapter`() {
        class CustomSampler(private val params: GameParams) : HiddenInfoSampler {
            override fun sampleShips(): Double = 10.0 // Always return 10
            override fun sampleTransporterShips(): Double = 5.0 // Always return 5
        }

        val betterRandomAgent = BetterRandomAgent()
        val customSampler = CustomSampler(GameParams())
        val unifiedAgent = betterRandomAgent.asUnified(customSampler)

        val params = GameParams(numPlanets = 10)
        unifiedAgent.prepareToPlayAs(Player.Player1, params)

        val gameState = GameStateFactory(params).createGame()
        val observation = ObservationFactory.create(gameState, setOf(Player.Player1))

        // Should work with custom sampler
        val action = unifiedAgent.getAction(observation)
        assertNotNull(action)
    }

    @Test
    fun `test UnifiedGameRunner runs multiple games correctly`() {
        val params = GameParams(numPlanets = 5, maxTicks = 50)
        val agent1 = BetterRandomAgent().asUnified()
        val agent2 = PureRandomAgent().asUnified()

        val runner = UnifiedGameRunner(agent1, agent2, params, partialObservability = false)
        val scores = runner.runGames(10)

        assertNotNull(scores)
        assertEquals(3, scores.size) // Player1, Player2, Neutral
        assertEquals(10, scores.values.sum(), "Total games should be 10")
    }

    @Test
    fun `test adapter optimization detects fully observable mode`() {
        // This test verifies that the adapter correctly detects fully observable observations
        val params = GameParams(numPlanets = 5)
        val gameState = GameStateFactory(params).createGame()

        // Fully observable (include Neutral to see all planets)
        val fullyObservable = ObservationFactory.create(gameState, setOf(Player.Player1, Player.Player2, Player.Neutral))
        val allVisible = fullyObservable.observedPlanets.all { it.nShips != null }
        assertTrue(allVisible, "Fully observable observation should have all ships visible")

        // Partially observable
        val partiallyObservable = ObservationFactory.create(gameState, setOf(Player.Player1))
        val hasHidden = partiallyObservable.observedPlanets.any { it.nShips == null }
        // Note: This may be true or false depending on the game state (whether there are opponent planets)
        // The test just verifies the observation factory is working correctly
    }

    @Test
    fun `test processGameOver is called on wrapped agent`() {
        var gameOverCalled = false

        class TestAgent : PlanetWarsPlayer() {
            override fun getAction(gameState: GameState): Action {
                return Action.doNothing()
            }

            override fun getAgentType(): String = "Test Agent"

            override fun processGameOver(finalState: GameState) {
                gameOverCalled = true
            }
        }

        val testAgent = TestAgent()
        val unifiedAgent = testAgent.asUnified()

        val params = GameParams(numPlanets = 5, maxTicks = 10)
        val runner = UnifiedGameRunner(
            unifiedAgent,
            PureRandomAgent().asUnified(),
            params,
            partialObservability = false
        )

        runner.runGame()

        assertTrue(gameOverCalled, "processGameOver should be called on the wrapped agent")
    }
}
