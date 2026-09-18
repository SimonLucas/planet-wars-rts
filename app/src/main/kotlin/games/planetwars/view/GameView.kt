package games.planetwars.view

import games.planetwars.core.*
import games.planetwars.runners.GameRunner
import util.Vec2d
import xkg.gui.*
import xkg.jvm.AppLauncher

class GameView(
    var gameState: GameState,
    val params: GameParams = GameParams(),
    val colors: ColorScheme = ColorScheme(),
    var gameRunner: GameRunner? = null,
    var paused: Boolean = false,
    var showInfoFor: Set<Player> = setOf(
        Player.Player1,
        Player.Player2,
        Player.Neutral,
    ),
) : XApp {

    private val width = params.width.toDouble()
    private val height = params.height.toDouble()
//    val gameRunner = GameRunner(gameState, params)

    override fun paint(xg: XGraphics) {
        val scaleX = xg.width() / width
        val scaleY = xg.height() / height
        val scale = minOf(scaleX, scaleY)

        val offsetX = (xg.width() / scale - width) / 2
        val offsetY = (xg.height() / scale - height) / 2

        xg.saveTransform()
        xg.setScale(scale, scale)
        xg.setTranslate(offsetX, offsetY)

        if (!paused) gameStep()

        drawBackground(xg)
        drawPlanets(xg)
        drawTransporters(xg)
        drawStatus(xg)

        xg.restoreTransform()
    }

    private fun gameStep() {
        val runner = gameRunner
        if (runner != null) {
            if (runner.forwardModel.isTerminal()) {
                println(runner.forwardModel.statusString())
                runner.newGame()
            }
            gameState = runner.stepGame().state
        }
    }

    private fun drawPlanets(xg: XGraphics) {
        for (planet in gameState.planets) {
            val color = colors.getColor(planet.owner)
            val size = 2 * planet.radius
            val circle = XEllipse(
                planet.position,
                size, size,
                XStyle(fg = color, fill = true, stroke = false)
            )
            xg.draw(circle)
            // draw the number of ships only if we are observing for the owner
            if (planet.owner !in showInfoFor) continue
            val tStyle = TStyle(fg = colors.text, size = 14.0)
            val text = XText("${planet.nShips.toInt()}", planet.position, tStyle)
            xg.draw(text)
        }
    }

    private fun drawTransporter(xg: XGraphics, transporter: Transporter) {
        // define the shape of the ship
//         static int[] xp = {-2, 0, 2, 0};
//        static int[] yp = {2, -2, 2, 0};
        val scale = 8.0
        val points = arrayListOf(
            Vec2d(-2.0, 2.0) * scale,
            Vec2d(0.0, 0.0) * scale,
            Vec2d(-2.0, -2.0) * scale,
            Vec2d(2.0, 0.0) * scale,
        )

        val color = colors.getColor(transporter.owner)

        val xPoly = XPoly(transporter.s, points, XStyle(fg = color, fill = true, stroke = false))
        xPoly.rotation = transporter.v.angle()
        xg.draw(xPoly)

        if (transporter.owner !in showInfoFor) return

        // draw the number of ships, but not rotated
        val tStyle = TStyle(fg = colors.text, size = 14.0)
        val text = XText("${transporter.nShips.toInt()}", transporter.s, tStyle)
        xg.draw(text)

    }

    private fun drawTransporters(xg: XGraphics) {
        for (planet in gameState.planets) {
            val transporter = planet.transporter
            if (transporter != null) {
                drawTransporter(xg, transporter)
            }
        }
    }

    private fun drawBackground(xg: XGraphics) {
        val centre = Vec2d(width / 2, height / 2)
        val rect = XRect(centre, width, height)
        rect.dStyle = XStyle(fg = colors.background, lineWidth = 10.0)
        xg.draw(rect)
    }

    private fun drawStatus(xg: XGraphics) {
        val runner = gameRunner ?: return
        val status = runner.forwardModel.statusString()
        val tStyle = TStyle(fg = colors.text, size = 14.0)
        val text = XText("Game status: $status", Vec2d(width / 2, 20.0), tStyle)
        xg.draw(text)
    }



    override fun handleKeyEvent(e: XKeyEvent) {
        if (e.t != XKeyEventType.Pressed) return
        println("Key event: $e")
        if (e.keyCode == ' '.code) {
            paused = !paused
        }
        // if keycode is 's' then slow down the frame rate
        // not we use the capitals to avoid the shift key
        if (e.keyCode == 'S'.code) {
            AppLauncher.globFrameRate /= 2.0
        }
        if (e.keyCode == 'F'.code) {
            AppLauncher.globFrameRate *= 2.0
            // limit the frame rate to 32fps
            AppLauncher.globFrameRate = minOf(AppLauncher.globFrameRate, 100.0)
        }
        println("Frame rate: ${AppLauncher.globFrameRate}")
        println('s'.code)
    }
}

fun main() {
    val params = GameParams(
        numPlanets = 10,
        initialNeutralRatio = 0.3,
        height = 200,
    )
    val gameState = GameStateFactory(params).createGame()
    for (planet in gameState.planets) {
        println(planet)
    }
    val title = "Planet Wars"
    AppLauncher(
        preferredWidth = params.width,
        preferredHeight = params.height,
        app = GameView(params = params, gameState = gameState),
        title = title
    ).launch()
}
