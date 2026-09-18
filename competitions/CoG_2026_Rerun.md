# CoG 2026 round-robin regeneration

The selected roster now contains **10 agents, one per entrant**, retaining
`metang-6ac59b9` and excluding `metagross-efaebe5`. The shared roster in
`app/src/main/python/league/cog_2026_config.py` controls the Markdown
and PNG exports.

## Regenerate the PNG

From the repository root:

```bash
./regen_cog_2026.sh
# Alternative using MetaGross:
./regen_cog_2026.sh --variant metagross
# Optional output directory:
./regen_cog_2026.sh --out-dir results/spring-2026
```

The default database is `~/spring-2026/new-league.db` and the default league is
**5**, the populated Spring 2026 pool. Outputs are
`~/spring-2026/round_robin_cog_2026_league5_metang.png` and `.md` by default.
The MetaGross alternative uses the `_metagross` suffix.
`--league ID`, `--db SQLALCHEMY_URL` and `--out-dir PATH` override those settings.
The `--variant` option accepts `metang` or `metagross`. The earlier 11-agent
`all` selection is no longer supported.

Each variant excludes the other mnn31 agent and all games involving that agent
from its table, recomputes each agent's mean win rate against the nine remaining
opponents, and sorts both outputs by that mean. Stored matches are untouched.
Unplayed opponents appear as `n/a` and are excluded from the mean.

## Selection evidence (18 September 2026)

The database identifies both entries as `mnn31/planet-wars-agent`:

| Entry | Agent ID | Commit | Database entry date |
| --- | --- | --- | --- |
| Metang | 54 | `6ac59b9306f0b9695ec1e454f1a97f098526065d` | 22 August 2026 |
| MetaGross | 60 | `efaebe58537f18e87d7275df77369a9e3693b027` | 30 August 2026 |

The source checkouts are under `~/spring-2026/agents/`. Comparing these exact
commits shows only two Dockerfile environment changes: `AGENT_BUDGET_MS`
35 → 30 and `AGENT_LEAGUE_BUDGET_MS` 150 → 185. The Kotlin code is identical.
These are qualifier and league search time budgets, so performance need not be
identical despite the common implementation. **MetaGross is the newer entry**;
Metang is retained as the requested representative, not on grounds of recency.

The presentation is `competitions/IEEE CoG 2026 Planet Wars RTS AI Results.pdf`;
the generated PNG can replace its page 12 heatmap. The PDF is not modified.
