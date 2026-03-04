# 🪐 PlanetWars AI Competition – Submission Instructions

Welcome to the PlanetWars AI competition! This document describes how to package and submit your entry. Your agent should run as a WebSocket server and respond to JSON-formatted messages. Each submission must include a `Dockerfile` that builds and runs your agent.

We support entries in **Kotlin/Java** or **Python**.  
However, you may use any language as long as your agent speaks **WebSocket** and uses **JSON**.

If you're entering a compeition linked to a conference, please
see create a set of slides following the instructions here.
[Slides Instructions](slides/README.md)
> For Kotlin/Java and Python, we provide example servers and agent wrappers so you can focus entirely on your agent logic.

---

## 🎮 Simulation-Based AI Support

The Kotlin framework includes a **Forward Model** to enable simulation-based AI methods such as **Monte Carlo Tree Search (MCTS)**.  
The Python version currently supports reactive agents, 
with forward model support a possibility for future releases.  
The Python option may be more suitable for neural network-based agents, 
as it allows you to use libraries like **PyTorch** or **TensorFlow**.

---

## 📦 Submission Format

Each submission must:

1. Contain all necessary code and dependencies to build and run your agent.
2. Include a working `Dockerfile` that listens on **port 8080** and runs your agent server.
3. Be able to receive JSON game states and return legal actions via **WebSocket on port 8080**.
4. Be self-contained — your Docker image must not require internet access at runtime.

---

## ☕ Kotlin/Java Submission

Your Kotlin or Java project must produce a single `.jar` file that runs the WebSocket server.

### Example `Dockerfile` (Self-Contained Multi-Stage Build - Recommended)

**Important:** Your Dockerfile should be **self-contained** and handle all building internally. This is the recommended approach:

```dockerfile
# ---------- Stage 1: Build with Gradle ----------
FROM gradle:8.5.0-jdk20 AS builder

WORKDIR /home/gradle/project

# Copy entire project into container
COPY . .

# Run Gradle build (skip tests for speed)
RUN gradle :app:build -x test

# ---------- Stage 2: Runtime with Java only ----------
FROM eclipse-temurin:20-jdk

WORKDIR /app

# Copy JAR from builder stage
COPY --from=builder /home/gradle/project/app/build/libs/*.jar app.jar

# Expose WebSocket port
EXPOSE 8080

# Run the agent
CMD ["java", "-jar", "app.jar"]
```

### Legacy Dockerfile (Still Supported)

For backward compatibility, the simple Dockerfile is still supported (expects pre-built JAR):

```dockerfile
FROM eclipse-temurin:20-jdk
WORKDIR /app
COPY app/build/libs/client-server.jar app.jar
EXPOSE 8080
CMD ["java", "-jar", "app.jar"]
```

**Note:** With this approach, the submission system will automatically run `./gradlew build` before building the Docker image. However, we recommend migrating to the self-contained approach above.

In your Gradle build file (`build.gradle.kts`), make sure to specify the correct entry point:

```kotlin
application {
    mainClass.set("competition_entry.RunEntryAsServerKt") // Adjust to match your actual package and file
}
```

### Example Kotlin Server Main

```kotlin
package competition_entry

import games.planetwars.agents.random.CarefulRandomAgent
import json_rmi.GameAgentServer

fun main() {
    val server = GameAgentServer(port = 8080, agentClass = CarefulRandomAgent::class)
    server.start(wait = true)
}
```


## ☕ Python Submission

As for the Kotlin/Java submission, your Python project must produce a 
single Docker image that runs the WebSocket server.

A complete example, including loading a pre-trained 
PyTorch Neural Network model is availale in
this public repository: https://github.com/Priwinn/planet-wars-rts/
Adapt this to your own agent logic and models.


---

## 📤 Submitting Your Agent via GitHub Issue

To enter the competition, simply **create a new GitHub Issue** in the [submissions repository](https://github.com/SimonLucas/planet-wars-rts-submissions/issues).

Your issue must contain a YAML block describing your submission, like this, 
noting the opening and closing triple backticks::

````yaml
```yaml
id: another-awesome-agent
repo_url: https://github.com/SimonLucas/planet-wars-rts/commit/9c1133cd88217abf99a892e89d95bae6fd0ed66b
commit: 9c1133cd88217abf99a892e89d95bae6fd0ed66b  # optional
```
````

### Important Notes:
- The `repo_url` should link to a **specific commit** (not just the repo root).
- The `commit` field is optional if it’s already included in the URL.
- If your repository is **private**, make sure to add `@SimonLucas` as a collaborator with read access.
- These results are provided for feedback; your agent will compete against a wider set of agents including submitted ones for the competition results

You will receive comments on your issue as your submission is processed, including:
- ✅ Confirmation of successful build
- 🧪 Evaluation results against baseline agents
- 📊 A Markdown-formatted results table similar to the one below (possibly with updated sample agents)
- 🏁 Final confirmation when the evaluation is complete

<img width="453" alt="image" src="https://github.com/user-attachments/assets/a67bb4f6-0dc7-42b9-9cd0-dda9d85c464b" />

---


Let us know if you have any questions. Good luck, and may the best agent win! 🚀
