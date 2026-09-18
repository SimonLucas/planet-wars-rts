"""Shared ten-entrant roster and corrected-run settings for CoG 2026."""

import os

# Use the populated Spring 2026 league; explicit overrides remain supported.
COG_LEAGUE_ID = int(os.environ.get("COG_LEAGUE_ID", "5"))
REMOTE_TIMEOUT_MS = 200

COG_2026_AGENTS = [
    "tail-small-2e3c0f7",
    "metang-6ac59b9",
    "anti-2-lite-aabb557",
    "selfplay-egocentric-7-2b99083",
    "teamtitansagentv3-256baf2",
    "gnn_cont999_128_top64-97050fd",
    "nanaboshi08281-8df146e",
    "sebba14-v2-9d3b196",
    "genetic_v1-04b0974",
    "galacticarmada-ecd6ae8",
]

METANG = "metang-6ac59b9"
METAGROSS = "metagross-efaebe5"


def selected_names(variant: str = "metang") -> list[str]:
    """Return one representative per entrant for the requested export."""
    if variant not in ("metang", "metagross"):
        raise ValueError(f"Unknown variant: {variant}")
    return [METAGROSS if name == METANG and variant == "metagross" else name
            for name in COG_2026_AGENTS]
