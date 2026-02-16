package games.planetwars.runners

import java.io.File

data class LeagueEntry(
    val agentName: String,
    var points: Double = 0.0,
    var nGames: Int = 0,
    var avgActionTime: Double = 0.0,
    var timeoutCount: Int = 0,

) {
    fun winRate(): Double {
        return 100 * points  / nGames
    }

}

data class LeagueResult(
    val entries: List<LeagueEntry>
) {
    fun getSortedEntries(): List<LeagueEntry> {
        return entries.sortedByDescending { it.winRate() }
    }
}

data class LeagueWriter(
    val outputDir: String = "results/sample/",
    val filename: String = "league.md",
) {

    fun generateMarkdownTable(league: LeagueResult): String {
        val sortedEntries = league.getSortedEntries()
        val header = "| Rank | Agent Name | Win Rate % | Played |\n|------|------------|----------|--------|\n"
        val rows = sortedEntries.mapIndexed { index, entry ->
            val formattedWinRate = "%.1f".format(entry.winRate())
            "| ${index + 1} | ${entry.agentName} | $formattedWinRate | ${entry.nGames} |"
        }.joinToString("\n")

        return header + rows
    }

    // Function to save the Markdown string to a file
    fun saveMarkdownToFile(markdownContent: String) {
        val dir = File(outputDir)
        if (!dir.exists()) dir.mkdirs() // Ensure the directory exists
        val outputFile = File(dir, filename)
        outputFile.writeText(markdownContent)
        println("League results saved to ${outputFile.absolutePath}")
    }
}

// Example usage
fun main() {
    val league = LeagueResult(
        listOf(
            LeagueEntry("AlphaBot", 10.0, 20),
            LeagueEntry("BetaAI", 8.0, 4),
            LeagueEntry("GammaSolver", 8.0, 3),
            LeagueEntry("DeltaAgent", 6.0, 5)
        )
    )

    val writer = LeagueWriter()
    val markdownContent = writer.generateMarkdownTable(league)
    writer.saveMarkdownToFile(markdownContent)
}
