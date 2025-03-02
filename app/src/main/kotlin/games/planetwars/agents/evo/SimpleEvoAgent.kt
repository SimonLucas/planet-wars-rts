package games.planetwars.agents.evo

import games.planetwars.agents.Action
import games.planetwars.agents.DoNothingAgent
import games.planetwars.agents.PlanetWarsAgent
import games.planetwars.agents.PlanetWarsPlayer
import games.planetwars.core.*
import kotlin.random.Random

data class GameStateWrapper(
    val gameState: GameState,
    val params: GameParams,
    val player: Player,
    val opponentModel: PlanetWarsAgent = DoNothingAgent(),
) {
    var forwardModel = ForwardModel(gameState, params)
    val shiftBy = 2

    fun getAction(gameState: GameState, from: Float, to: Float): Action {
        // filter the planets that are owned by the player AND have a transporter available
        val myPlanets = gameState.planets.filter { it.owner == player && it.transporter == null }
        // filter the planets that are owned by the player AND have a transporter available
        if (myPlanets.isEmpty()) {
            return Action.doNothing()
        }
        // now find a random target planet
        val otherPlanets = gameState.planets.filter { it.owner == player.opponent() || it.owner == Player.Neutral }
        if (otherPlanets.isEmpty()) {
            return Action.doNothing()
        }
        val source = myPlanets[(from * myPlanets.size).toInt()]
        val target = otherPlanets[(to * otherPlanets.size).toInt()]
        return Action(player, source.id, target.id, source.nShips / 2)
    }

    fun runForwardModel(seq: FloatArray): Double {
        var ix = 0;
        forwardModel = ForwardModel(gameState.deepCopy(), params)
        while (ix < seq.size && !forwardModel.isTerminal()) {
            val from = seq[ix]
            val to = seq[ix + 1]
            val myAction = getAction(gameState, from, to)
            val opponentAction = opponentModel.getAction(gameState)
            val actions = mapOf(player to myAction, player.opponent() to opponentAction)
            forwardModel.step(actions)
            ix += shiftBy
        }
        return scoreDifference()
    }

    fun scoreDifference(): Double {
        // allow standalone use of this as well
        return forwardModel.getShips(player) - forwardModel.getShips(player.opponent())
    }
}

data class SimpleEvoAgent(
    var flipAtLeastOneValue: Boolean = true,
    var probMutation: Double = 0.2,
    var sequenceLength: Int = 200,
    var nEvals: Int = 20,
    var useShiftBuffer: Boolean = true,
    var epsilon: Double = 1e-6,
    var timeLimitMillis: Long = 10,

    ) : PlanetWarsPlayer() {
    override fun getAgentType(): String {
        return "EvoAgent-$sequenceLength-$nEvals-$probMutation-$useShiftBuffer"
    }

    internal var random = Random

    // these are all the parameters that control the agend
//    internal var buffer: FloatArray? = null // randomPoint(sequenceLength)


    var bestSolution: ScoredSolution? = null

    var x: Int? = 1

    data class ScoredSolution(val score: Double, val solution: FloatArray)

    override fun getAction(gameState: GameState): Action {
        val wrapper = GameStateWrapper(gameState.deepCopy(), params, player)
        if (bestSolution == null) {
            val solution = randomPoint()
            bestSolution = ScoredSolution(evalSeq(wrapper, solution), solution)
        }
        if (useShiftBuffer) {
            val nextSeq = shiftLeftAndRandomAppend(bestSolution!!.solution, wrapper.shiftBy)
            bestSolution = ScoredSolution(evalSeq(wrapper, nextSeq), nextSeq)
        } else {
            val nextSeq = randomPoint()
            bestSolution = ScoredSolution(evalSeq(wrapper, nextSeq), nextSeq)
        }
        val best = bestSolution ?: return Action.doNothing()

        for (i in 0 until nEvals) {
            val mut = mutate(best.solution, probMutation)
            val mutScore = evalSeq(wrapper, mut)
            if (mutScore >= best.score) {
                bestSolution = ScoredSolution(mutScore, mut)
            }
        }
        val action = wrapper.getAction(gameState, best.solution[0], best.solution[1])
        return action
    }

    private fun mutate(v: FloatArray, mutProb: Double): FloatArray {

        val n = v.size
        val x = FloatArray(n)
        // pointwise probability of additional mutations
        // choose element of vector to mutate
        var ix = random.nextInt(n)
        if (!flipAtLeastOneValue) {
            // setting this to -1 means it will never match the first clause in the if statement in the loop
            // leaving it at the randomly chosen value ensures that at least one bit (or more generally value) is always flipped
            ix = -1
        }
        // copy all the values faithfully apart from the chosen one
        for (i in 0 until n) {
            if (i == ix || random.nextDouble() < mutProb) {
                x[i] = random.nextFloat()
            } else {
                x[i] = v[i]
            }
        }
        return x
    }

    // random point in n-dimensional space in unit hypercube; n = sequenceLength
    private fun randomPoint(): FloatArray {
        val p = FloatArray(sequenceLength)
        for (i in p.indices) {
            p[i] = random.nextFloat()
        }
        return p
    }

    // todo: change this to use a circular buffer to avoid all the shifting

    private fun shiftLeftAndRandomAppend(v: FloatArray, shiftBy: Int): FloatArray {
        val p = FloatArray(v.size)
        for (i in 0 until p.size - shiftBy) {
            p[i] = v[i + shiftBy]
        }
        // TODO: this is a bit of a hack, but it should work when shiftBy is 2, which it is for now
        p[p.size - 1] = random.nextFloat()
        p[p.size - 2] = random.nextFloat()
        return p
    }

    private fun evalSeq(wrapper: GameStateWrapper, seq: FloatArray): Double {
        wrapper.runForwardModel(seq)
        return wrapper.scoreDifference()
    }

}

fun main() {
    val gameParams = GameParams(numPlanets = 10)
    val gameState = GameStateFactory(gameParams).createGame()
    val agent = SimpleEvoAgent()
    agent.prepareToPlayAs(Player.Player1, gameParams)
    println(agent.getAgentType())
    val action = agent.getAction(gameState)
    println(action)
}