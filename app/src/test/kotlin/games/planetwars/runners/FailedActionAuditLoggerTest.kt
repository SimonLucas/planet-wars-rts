package games.planetwars.runners

import games.planetwars.agents.Action
import games.planetwars.core.FailedActionEvent
import games.planetwars.core.Player
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.nio.file.Path
import kotlin.io.path.readLines
import kotlin.test.assertContains
import kotlin.test.assertEquals

class FailedActionAuditLoggerTest {
    @TempDir
    lateinit var tempDir: Path

    @Test
    fun `audit record identifies agent opponent action and reason`() {
        val logPath = tempDir.resolve("failed-actions.jsonl")
        val logger = FailedActionAuditLogger(logPath.toString())
        val event = FailedActionEvent(
            gameTick = 17,
            player = Player.Player2,
            action = Action(Player.Player2, 1, 99, -5.0),
            reason = "invalid_destination_planet"
        )

        logger.log("Suspect Agent", "Opponent Agent", event)

        val lines = logPath.readLines()
        assertEquals(1, lines.size)
        assertContains(lines.single(), "\"agentName\":\"Suspect Agent\"")
        assertContains(lines.single(), "\"opponentName\":\"Opponent Agent\"")
        assertContains(lines.single(), "\"gameTick\":17")
        assertContains(lines.single(), "\"reason\":\"invalid_destination_planet\"")
        assertContains(lines.single(), "\"numShips\":-5.0")
    }
}
