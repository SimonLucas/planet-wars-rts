package games.planetwars.partial

import games.planetwars.agents.RemotePartialObservationAgent
import games.planetwars.core.Player
import io.ktor.server.engine.*
import io.ktor.server.netty.*
import io.ktor.server.application.*
import io.ktor.server.routing.*
import io.ktor.server.websocket.*
import io.ktor.websocket.*
import json_rmi.*
import kotlinx.coroutines.channels.consumeEach
import kotlinx.serialization.PolymorphicSerializer
import kotlinx.serialization.json.*
import java.util.*
import kotlin.reflect.KClass
import kotlin.reflect.KParameter
import kotlin.reflect.full.createInstance

class PartialGameAgentServer(
    private val port: Int,
    private val agentClass: KClass<out RemotePartialObservationAgent>
) {
    private var server: ApplicationEngine? = null
    private val agentMap = mutableMapOf<String, RemotePartialObservationAgent>()
    private var frameCount = 0

    fun start(wait: Boolean = true) {
        println("Starting PartialGameAgentServer on port $port with agent class ${agentClass.simpleName}...")
        server = embeddedServer(Netty, port = port) {
            install(WebSockets)
            routing {
                webSocket("/ws") {
                    incoming.consumeEach { frame ->
                        frameCount++
                        if (frame is Frame.Text) {
                            val request = json.decodeFromString<RemoteInvocationRequest>(frame.readText())
                            println("Frame $frameCount; Received: $request")
                            println("Keys: ${agentMap.keys}")

                            val response = try {
                                when (request.requestType) {
                                    RpcConstants.TYPE_INIT -> {
                                        val id = UUID.randomUUID().toString()
                                        val instance = agentClass.createInstance()
                                        agentMap[id] = instance
                                        RemoteInvocationResponse("ok", json.encodeToJsonElement(mapOf("objectId" to id)))
                                    }

                                    RpcConstants.TYPE_INVOKE -> {
                                        val agent = agentMap[request.objectId] ?: error("No such object")
                                        val kFunction = agent::class.members.firstOrNull { it.name == request.method }
                                            ?: error("Unknown method: ${request.method}")
                                        val params = kFunction.parameters.drop(1).mapIndexed { i, p ->
                                            decodeArgument(p, request.args[i])
                                        }
                                        val result = kFunction.call(agent, *params.toTypedArray())

                                        val encodedResult = when (result) {
                                            is RemoteConstructable -> json.encodeToJsonElement(
                                                PolymorphicSerializer(RemoteConstructable::class), result
                                            )
                                            is Player -> json.encodeToJsonElement(Player.serializer(), result)
                                            is String -> JsonPrimitive(result)
                                            is Int -> JsonPrimitive(result)
                                            is Double -> JsonPrimitive(result)
                                            is Boolean -> JsonPrimitive(result)
                                            null -> JsonNull
                                            else -> error("Cannot serialize result of type: ${result::class.simpleName}")
                                        }
                                        RemoteInvocationResponse("ok", encodedResult)
                                    }

                                    RpcConstants.TYPE_END -> {
                                        val removed = agentMap.remove(request.objectId)
                                        val msg = if (removed != null) "Agent removed" else "No such agent"
                                        RemoteInvocationResponse("ok", json.encodeToJsonElement(mapOf("message" to msg)))
                                    }

                                    else -> throw IllegalArgumentException("Unknown request type: ${request.requestType}")
                                }
                            } catch (e: Exception) {
                                e.printStackTrace()
                                RemoteInvocationResponse("error", error = e.message)
                            }

                            send(json.encodeToString(RemoteInvocationResponse.serializer(), response))
                        }
                    }
                }
            }
        }.start(wait = wait)
    }

    fun stop() {
        server?.stop(gracePeriodMillis = 1000, timeoutMillis = 2000)
        println("GameAgentServer stopped agent $agentClass after $frameCount frames.")
    }

    private fun decodeArgument(p: KParameter, jsonArg: JsonElement): Any = when (p.type.classifier) {
        Player::class -> json.decodeFromJsonElement(Player.serializer(), jsonArg)
        String::class -> jsonArg.jsonPrimitive.content
        Int::class -> jsonArg.jsonPrimitive.int
        Double::class -> jsonArg.jsonPrimitive.double
        Boolean::class -> jsonArg.jsonPrimitive.boolean
        else -> json.decodeFromJsonElement(PolymorphicSerializer(RemoteConstructable::class), jsonArg)
    }
}
