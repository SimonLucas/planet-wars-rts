// File: Server.kt
import games.planetwars.agents.PlanetWarsAgent
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
import kotlin.reflect.KParameter
import kotlin.reflect.full.createInstance

//fun decodeArgument(p: KParameter, jsonArg: JsonElement): Any? = when (p.type.classifier) {
//    Player::class -> json.decodeFromJsonElement(Player.serializer(), jsonArg)
//    else -> json.decodeFromJsonElement(PolymorphicSerializer(RemoteConstructable::class), jsonArg)
//}


fun decodeArgument(p: KParameter, jsonArg: JsonElement): Any = when (p.type.classifier) {
    Player::class -> json.decodeFromJsonElement(Player.serializer(), jsonArg)
    String::class -> jsonArg.jsonPrimitive.content
    Int::class -> jsonArg.jsonPrimitive.int
    Double::class -> jsonArg.jsonPrimitive.double
    Boolean::class -> jsonArg.jsonPrimitive.boolean
    else -> json.decodeFromJsonElement(PolymorphicSerializer(RemoteConstructable::class), jsonArg)
}

fun main() {
    embeddedServer(Netty, port = 8080) {
        install(WebSockets)
        routing {
            webSocket("/ws") {
                val agentMap = mutableMapOf<String, PlanetWarsAgent>()

                incoming.consumeEach { frame ->
                    if (frame is Frame.Text) {
                        val request = json.decodeFromString<RemoteInvocationRequest>(frame.readText())
                        println("Received: $request")

                        val response = try {
                            when (request.requestType) {
                                RpcConstants.TYPE_INIT -> {
                                    val id = UUID.randomUUID().toString()
                                    val className = request.className ?: error("Missing className in init request")
                                    val clazz = Class.forName(className).kotlin
                                    val instance = clazz.createInstance() as PlanetWarsAgent
                                    agentMap[id] = instance
                                    println("In INIT $agentMap")
                                    RemoteInvocationResponse("ok", json.encodeToJsonElement(mapOf("objectId" to id)))
                                }
                                RpcConstants.TYPE_INVOKE -> {
                                    val agent = agentMap[request.objectId] ?: error("No such object")
                                    val kFunction = agent::class.members.firstOrNull { it.name == request.method } ?: error("Unknown method: ${request.method}")
                                    val params = kFunction.parameters.drop(1).mapIndexed { i, p ->
                                        decodeArgument(p, request.args[i])
                                    }
                                    println("In INVOKE: params $params")
                                    val result = kFunction.call(agent, *params.toTypedArray())
                                    println("In INVOKE: result $result")

                                    val encodedResult = when (result) {
                                        is RemoteConstructable -> json.encodeToJsonElement(PolymorphicSerializer(RemoteConstructable::class), result)
                                        is Player -> json.encodeToJsonElement(Player.serializer(), result)
                                        is String -> JsonPrimitive(result)
                                        is Int -> JsonPrimitive(result)
                                        is Double -> JsonPrimitive(result)
                                        is Boolean -> JsonPrimitive(result)
                                        null -> JsonNull
                                        else -> error("Cannot serialize result of type: ${result::class.simpleName}")
                                    }
//                                    val encodedResult = when (result) {
//                                        is RemoteConstructable -> json.encodeToJsonElement(PolymorphicSerializer(RemoteConstructable::class), result)
//                                        is Player -> json.encodeToJsonElement(Player.serializer(), result)
//                                        null -> JsonNull
//                                        else -> error("Cannot serialize result of type: ${result::class.simpleName}")
//                                    }
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
    }.start(wait = true)
}
