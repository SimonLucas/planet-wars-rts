package competition_entry

import games.planetwars.partial.PartialGameAgentServer

fun main() {
    val server = PartialGameAgentServer(port = 7080, agentClass = CarefulPartialAgent::class)
    server.start(wait = true)
}
