package games.planetwars.runners

import games.planetwars.core.FailedActionEvent
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import java.io.File

@Serializable
private data class FailedActionAuditRecord(
    val timestampMillis: Long,
    val agentName: String,
    val opponentName: String,
    val event: FailedActionEvent
)

class FailedActionAuditLogger(
    logFilePath: String = System.getenv("FAILED_ACTION_LOG") ?: "log_data/failed_actions.jsonl"
) {
    private val logFile = File(logFilePath)
    private val json = Json { encodeDefaults = true }

    init {
        logFile.parentFile?.mkdirs()
    }

    @Synchronized
    fun log(agentName: String, opponentName: String, event: FailedActionEvent) {
        val record = FailedActionAuditRecord(
            timestampMillis = System.currentTimeMillis(),
            agentName = agentName,
            opponentName = opponentName,
            event = event
        )
        logFile.appendText(json.encodeToString(record) + "\n")
    }
}
