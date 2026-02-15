# Simple Agent Battle Examples

This directory contains simple, easy-to-understand examples for cloning, launching, and evaluating Planet Wars agents.

## Overview

These scripts demonstrate how to:
1. **Clone** agent repositories from GitHub
2. **Build** agents and create Podman containers
3. **Launch** agent servers
4. **Run games** between agents
5. **Display results**
6. **Clean up** containers

## Prerequisites

### Required Software
- **Python 3.8+** with virtual environment activated
- **Podman** installed and running
  ```bash
  podman --version  # Should show version 4.0+
  ```
- **Java 21+** (for building Kotlin agents)
- **Gradle** wrapper (included in repos)

### Environment Setup
```bash
# Set PYTHONPATH
export PYTHONPATH=/Users/eex250/GitHub/planet-wars-rts/app/src/main/python

# Activate virtual environment (if using one)
source .venv/bin/activate
```

### GitHub Token (for private repos)
If cloning private repositories, create a GitHub personal access token and save it:
```bash
echo "your_github_token_here" > ~/.github_submission_token
```

## Examples

### 1. Local Python Battle (`local_python_battle.py`) ⭐ **START HERE**

**The simplest way to test agents** - runs local Python agents without containers.

```bash
python3 -m examples.local_python_battle
```

**What it does:**
- Runs two Python agents directly (no cloning, no containers)
- Tests both fully and partially observable modes
- Completes in seconds
- Perfect for learning and quick testing

**Customize by editing the agent choices:**
```python
agent1 = as_unified(PureRandomAgent())
agent2 = as_unified(CarefulRandomAgent())

# Or use other agents like:
# agent1 = as_unified(GreedyHeuristicAgent())
```

**Expected output:**
```
======================================================================
LOCAL PYTHON AGENT BATTLE
======================================================================

🤖 Agent 1: PureRandomAgent
🤖 Agent 2: CarefulRandomAgent
🎮 Games: 10

======================================================================
FULLY OBSERVABLE MODE
======================================================================

🎮 Playing 10 games...

📊 Results (Fully Observable):
   PureRandomAgent (Player1): 0 wins
   CarefulRandomAgent (Player2): 10 wins

======================================================================
PARTIALLY OBSERVABLE MODE
======================================================================

🎮 Playing 10 games...

📊 Results (Partially Observable):
   PureRandomAgent (Player1): 0 wins
   CarefulRandomAgent (Player2): 10 wins

======================================================================
COMPARISON
======================================================================

How observability affects the agents:
  Fully Observable:     PureRandomAgent won 0/10
  Partially Observable: PureRandomAgent won 0/10

✨ Done!
```

---

### 2. Minimal Agent Battle (`minimal_agent_battle.py`) 🚀

**For testing external agent repositories** - clones, builds, and launches in containers.

**⚠️ Requirements:**
- Podman installed and running
- GitHub token configured
- Target repositories must have compatible Java versions
- Dockerfile present in repositories

```bash
python3 -m examples.minimal_agent_battle
```

**Customize by editing these variables at the top of the file:**
```python
AGENT_1 = AgentEntry(
    id="my-agent-v1",
    repo_url="https://github.com/username/planet-wars-rts.git",
    commit="abc123"  # Optional: None for latest
)

AGENT_2 = AgentEntry(
    id="my-agent-v2",
    repo_url="https://github.com/username/planet-wars-rts.git",
    commit="def456"  # Optional: None for latest
)

NUM_GAMES = 10  # How many games to play
```

**What it does:**
- Clones both repositories
- Builds and launches in Podman containers
- Plays N games between them
- Shows average scores and winner
- Cleans up containers

**Expected output:**
```
🤖 Agent 1: my-agent-v1
🤖 Agent 2: my-agent-v2
🎮 Games: 10

🚀 Launching agents (this may take a minute)...

🎮 Playing 10 games...

📊 Results:
   my-agent-v1: 45.3
   my-agent-v2: 54.7

🏆 Winner: my-agent-v2

🧹 Cleaning up containers...
✨ Done!
```

---

### 3. Simple Agent Battle (`simple_agent_battle.py`) 📝

**More detailed version** with step-by-step output and explanations.

```bash
python3 -m examples.simple_agent_battle
```

**What it does:**
- Same as minimal version but with:
  - Detailed progress messages for each step
  - More informative output
  - Optional full Gradle output display
  - Better error handling and reporting

**When to use:**
- When you want to understand what's happening at each step
- When debugging issues
- When learning the workflow for the first time

---

## How It Works

### Step-by-Step Process

1. **Define Agents**
   ```python
   agent = AgentEntry(
       id="unique-agent-name",
       repo_url="https://github.com/user/repo.git",
       commit="abc123"  # Optional
   )
   ```

2. **Launch Agent** (handled by `launch_agent()`)
   - Clones repository to work directory
   - Checks out specified commit (if provided)
   - Runs `./gradlew build` to compile project
   - Builds Podman image from Dockerfile
   - Starts container with port mapping (8080 → random port)
   - Returns allocated port number

3. **Run Games** (handled by `run_remote_pair_evaluation()`)
   - Calls Kotlin evaluation code via Gradle
   - Connects to both agent servers via WebSocket
   - Plays N games with agents alternating roles
   - Returns average scores for each agent

4. **Cleanup** (handled by `stop_and_remove_container()`)
   - Stops running containers
   - Removes containers
   - Frees up system resources

---

## Customization Guide

### Testing Different Commits

Compare two versions of the same agent:
```python
AGENT_1 = AgentEntry(
    id="agent-v1",
    repo_url="https://github.com/user/planet-wars-rts.git",
    commit="older-commit-hash"
)

AGENT_2 = AgentEntry(
    id="agent-v2",
    repo_url="https://github.com/user/planet-wars-rts.git",
    commit="newer-commit-hash"
)
```

### Testing Against Different Opponents

```python
AGENT_1 = AgentEntry(
    id="my-agent",
    repo_url="https://github.com/me/planet-wars-rts.git"
)

AGENT_2 = AgentEntry(
    id="opponent-agent",
    repo_url="https://github.com/them/planet-wars-rts.git"
)
```

### Adjusting Number of Games

```python
NUM_GAMES = 100  # More games = more reliable statistics
```

### Changing Work Directory

```python
WORK_DIR = Path("/tmp/agent-battles")  # Use temp directory
# or
WORK_DIR = Path.home() / "my-agents"   # Use home directory
```

---

## Troubleshooting

### "Could not find 'gradlew' up the tree"
**Problem:** Script can't find project root.
**Solution:** Run from within the planet-wars-rts repository.

### "No module named 'runner_utils'"
**Problem:** PYTHONPATH not set correctly.
**Solution:**
```bash
export PYTHONPATH=/path/to/planet-wars-rts/app/src/main/python
```

### "Podman command not found"
**Problem:** Podman not installed.
**Solution:**
```bash
# macOS
brew install podman
podman machine init
podman machine start

# Linux
sudo apt install podman  # or yum/dnf
```

### "Failed to prepare agent"
**Problem:** Clone or build failed.
**Solution:**
- Check internet connection
- Verify repository URL is correct
- Ensure commit hash exists
- Check GitHub token if cloning private repo
- Look for Gradle build errors in output

### "WebSocket connection failed"
**Problem:** Agent server not responding.
**Solution:**
- Increase wait time after launch (change `time.sleep(5)` to `time.sleep(10)`)
- Check container logs: `podman logs container-{agent-id}`
- Verify port is not blocked by firewall

### Containers Not Cleaned Up
**Problem:** Containers still running after script exits.
**Solution:** Manually clean up:
```bash
# List all agent containers
podman ps -a | grep container-

# Remove specific container
podman rm -f container-agent-name

# Remove all agent containers
podman ps -a | grep "container-" | awk '{print $1}' | xargs podman rm -f
```

---

## Advanced Usage

### Running Multiple Battles

Create a script to test multiple agent combinations:

```python
agents = [
    AgentEntry(id="agent-a", repo_url="...", commit="..."),
    AgentEntry(id="agent-b", repo_url="...", commit="..."),
    AgentEntry(id="agent-c", repo_url="...", commit="..."),
]

results = {}
for i in range(len(agents)):
    for j in range(i+1, len(agents)):
        # Launch, evaluate, cleanup agents[i] vs agents[j]
        # Store results
        pass
```

### Saving Results to File

```python
import json

results = {
    "agent1": AGENT_1.id,
    "agent2": AGENT_2.id,
    "games": NUM_GAMES,
    "avg1": avg1,
    "avg2": avg2,
    "winner": "agent1" if avg1 > avg2 else "agent2"
}

with open("battle_results.json", "w") as f:
    json.dump(results, f, indent=2)
```

---

## See Also

- **Full infrastructure**: See `/app/src/main/python/league/` for advanced league system
- **Database-backed evaluation**: See `run_agents_from_db.py` for persistent tracking
- **Automated submissions**: See `submission_evaluator_bot.py` for GitHub integration
- **Agent server framework**: See `game_agent_server.py` for creating your own agent servers

---

## Quick Reference

### Essential Commands

```bash
# Run minimal example
python3 -m examples.minimal_agent_battle

# Run detailed example
python3 -m examples.simple_agent_battle

# List running containers
podman ps

# View container logs
podman logs container-{agent-id}

# Stop all agent containers
podman stop $(podman ps -q --filter "name=container-")

# Remove all agent containers
podman rm -f $(podman ps -aq --filter "name=container-")

# List agent images
podman images | grep game-server
```

### Key Files in Infrastructure

- `runner_utils/agent_entry.py` - Agent data models
- `runner_utils/clone_utils.py` - Repository cloning
- `runner_utils/launch_agent.py` - Container launching
- `league/run_pair_eval.py` - Game evaluation
- `runner_utils/shut_down_all_containers.py` - Cleanup utilities

---

**Happy battling! 🤖⚔️🤖**
