package json_rmi


import games.planetwars.agents.Action
import kotlinx.serialization.modules.SerializersModule
import kotlinx.serialization.modules.polymorphic
import kotlinx.serialization.modules.subclass
import games.planetwars.core.*

val customSerializersModule = SerializersModule {
    polymorphic(RemoteConstructable::class) {
        subclass(RemoteInvocationRequest::class, RemoteInvocationRequest.serializer())
        subclass(RemoteInvocationResponse::class, RemoteInvocationResponse.serializer())
        subclass(GameState::class, GameState.serializer())
        subclass(GameParams::class, GameParams.serializer())
//        subclass(Player::class, Player.serializer())
        subclass(Action::class, Action.serializer())
        subclass(Planet::class, Planet.serializer())
        subclass(Transporter::class, Transporter.serializer())
        // Add more as needed
        // 🆕 Add the partially observable data types:
        subclass(Observation::class, Observation.serializer())
        subclass(PlanetObservation::class, PlanetObservation.serializer())
        subclass(TransporterObservation::class, TransporterObservation.serializer())

    }
}
