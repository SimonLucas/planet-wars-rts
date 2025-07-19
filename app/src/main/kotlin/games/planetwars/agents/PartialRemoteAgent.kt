package games.planetwars.agents


import games.planetwars.core.*
import io.ktor.client.*
import io.ktor.client.engine.cio.*
import io.ktor.client.plugins.websocket.*
import io.ktor.websocket.*
import json_rmi.*
import kotlinx.coroutines.*
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject

class PartialRemoteAgent(
    private val className: String,
    private val port: Int = 8080,
    private val logger: JsonLogger = JsonLogger()
) : RemotePartialObservationPlayer() {

    private val serverUrl = "ws://localhost:$port/ws"
    private val client = HttpClient(CIO) {
        install(WebSockets)
    }

    private lateinit var session: DefaultClientWebSocketSession
    private lateinit var objectId: String
    private var connected = false

    private suspend fun connectOnceIfNeeded() {
        if (!connected) {
            session = client.webSocketSession(serverUrl)
            objectId = initAgent(session, className, logger)  // ✅ fixed argument order
            connected = true
        }
    }

    override fun prepareToPlayAs(player: Player, params: GameParams, opponent: String?): String = runBlocking {
        connectOnceIfNeeded()
        invokeRemoteMethod(
            session = session,
            objectId = objectId,
            method = "prepareToPlayAs",
            args = listOf(player, params, opponent ?: "Anonymous"),
            logger = logger
        )
        getAgentType()
    }

    override fun getAction(observation: Observation): Action = runBlocking {
        connectOnceIfNeeded()
        val response = invokeRemoteMethod(
            session = session,
            objectId = objectId,
            method = "getAction",
            args = listOf(observation),
            logger = logger
        )
        val jsonResp = json.parseToJsonElement(response).jsonObject
        val result = jsonResp["result"]
        if (result != null && result is JsonObject) {
            json.decodeFromJsonElement(Action.serializer(), result)
        } else {
            Action.doNothing()
        }
    }

    override fun getAgentType(): String = runBlocking {
        connectOnceIfNeeded()
        val response = invokeRemoteMethod(
            session = session,
            objectId = objectId,
            method = "getAgentType",
            args = emptyList(),
            logger = logger
        )
        val jsonResp = json.parseToJsonElement(response).jsonObject
        val result = jsonResp["result"]
        val type = result?.toString()?.trim('"') ?: "Remote[$className]"
        "$type (Remote)"
    }

    override fun processGameOver(finalState: GameState) = runBlocking {
        if (connected) {
            invokeRemoteMethod(
                session = session,
                objectId = objectId,
                method = "processGameOver",
                args = listOf(finalState),
                logger = logger
            )
            endAgent(session, objectId, logger)  // ✅ fixed argument order
            session.close()
            client.close()
            connected = false
        }
    }
}
