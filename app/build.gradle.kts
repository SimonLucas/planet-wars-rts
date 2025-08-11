//plugins {
//    kotlin("jvm") version "1.9.10"
//    kotlin("plugin.serialization") version "1.9.10"
//    application
//}

plugins {
    kotlin("jvm") version "1.9.10"
    kotlin("plugin.serialization") version "1.9.10"
    application
    id("com.github.johnrengelman.shadow") version "8.1.1" // Add shadow plugin
}



repositories {
    mavenCentral()
}

group = "sml"
version = "1.0-SNAPSHOT"

dependencies {
    // Kotlin Standard Library
    implementation("org.jetbrains.kotlin:kotlin-stdlib:1.9.10")

    // Ktor dependencies
    implementation("io.ktor:ktor-server-core:2.3.3")
    implementation("io.ktor:ktor-server-netty:2.3.3")
    implementation("io.ktor:ktor-server-websockets:2.3.3")
    implementation("io.ktor:ktor-client-core:2.3.3")
    implementation("io.ktor:ktor-client-cio:2.3.3")
    implementation("io.ktor:ktor-server-content-negotiation:2.3.3")
    implementation("io.ktor:ktor-serialization-kotlinx-json:2.3.3")

    // Kotlinx Serialization
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.5.1")

    // Coroutines
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.7.3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-jdk8:1.7.3")

    // Testing
    testImplementation("org.jetbrains.kotlin:kotlin-test-junit5")
    testImplementation("org.junit.jupiter:junit-jupiter-engine:5.10.0")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")

    // Additional Libraries
    implementation("com.google.guava:guava:32.1.2-jre")
}
tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}

tasks.withType<Jar> {
    manifest {
        attributes["Main-Class"] = "client_server.MultiRTSServer"
    }
}

tasks.named<com.github.jengelman.gradle.plugins.shadow.tasks.ShadowJar>("shadowJar") {
    archiveBaseName.set("client-server")
    archiveClassifier.set("")
    archiveVersion.set("")
}

//tasks.withType<com.github.jengelman.gradle.plugins.shadow.tasks.ShadowJar> {
//    archiveBaseName.set("client-server")
//    archiveClassifier.set("")
//    archiveVersion.set("")
//}


java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(20) // Downgraded to Java 20 for compatibility
    }
}

application {
    mainClass.set("competition_entry.RunEntryAsServerKt") // Adjust this if your package structure is different
}

kotlin {
    jvmToolchain(20) // Ensure Kotlin targets JVM 20 as well
}

tasks.register<JavaExec>("runEvaluation") {
    mainClass.set("games.planetwars.runners.EvaluateAgentKt")
    classpath = sourceSets["main"].runtimeClasspath
    args = listOf(project.findProperty("args")?.toString() ?: "49875")
}
tasks.register<JavaExec>("runRemotePairEvaluation") {
    // Kotlin entry point above
    mainClass.set("games.planetwars.runners.RunRemotePairEvaluationKt")
    classpath = sourceSets["main"].runtimeClasspath

    // Support `--args=portA,portB,gpp,timeout` (comes in as a project property)
    val raw = project.findProperty("args")?.toString()
    args = if (raw != null) listOf(raw) else listOf("5001,5002,10,50")
}
