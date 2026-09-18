#!/usr/bin/env python3
"""
Slide-friendly PNG heatmap of the CoG 2026 round-robin results.

Rows = agents (numbered + name), columns = agent numbers only.
Cell colour encodes the row agent's win rate vs the column agent.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from league.init_db import get_default_db_path
from league.round_robin_top_n import fetch_agents_by_name, compute_head_to_head

from league.cog_2026_config import COG_2026_AGENTS, COG_LEAGUE_ID
import re

OUT_PATH = Path.home() / "spring-2026" / f"round_robin_cog_2026_league{COG_LEAGUE_ID}_metang.png"

CMAP = mpl.colormaps["RdYlGn"]
DIAG_COLOR = "#cccccc"
NA_COLOR = "#eeeeee"
NA_TEXT_COLOR = "#aaaaaa"


def _win_rate_color(wr: float) -> tuple:
    """Map win rate 0–100 to RdYlGn colour."""
    return CMAP(wr / 100.0)


def generate(out_path: Path = OUT_PATH, *, league_id: int = COG_LEAGUE_ID,
             names: list[str] | None = None, db_url: str | None = None) -> None:
    names = COG_2026_AGENTS if names is None else names
    engine = create_engine(db_url or get_default_db_path(), future=True)
    with Session(engine) as session:
        agents = fetch_agents_by_name(session, league_id, names)
        # Preserve the caller's ordering for consistent Markdown and PNG tables.
        name_to_agent = {a["name"]: a for a in agents}
        agents = [name_to_agent[n] for n in names if n in name_to_agent]

        agent_ids = [a["agent_id"] for a in agents]
        h2h = compute_head_to_head(session, league_id, agent_ids)

    n = len(agents)

    # Build win-rate matrix (NaN = no games / diagonal)
    wr_matrix = np.full((n, n), np.nan)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            wins, games = h2h.get((agent_ids[i], agent_ids[j]), (0, 0))
            if games > 0:
                wr_matrix[i, j] = 100.0 * wins / games

    # ── Layout ────────────────────────────────────────────────────────────────
    fig_w, fig_h = 16, 7
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(0, n + 1)   # col 0 = row-label col, cols 1..n = data
    ax.set_ylim(0, n + 1)   # row 0 = header, rows 1..n = data (top-down below)
    ax.axis("off")
    ax.set_aspect("auto")

    LABEL_COL_W = 2.8   # relative width units for the name column
    DATA_COL_W = 0.675  # 10% narrower to accommodate the Avg column
    total_w = LABEL_COL_W + (n + 1) * DATA_COL_W

    # Re-set xlim to match actual column layout
    ax.set_xlim(0, total_w)
    ax.set_ylim(0, n + 1)

    row_h = 1.0  # each row is 1 unit tall

    def col_x(j: int) -> float:
        """Left edge of data column j (0-indexed)."""
        return LABEL_COL_W + j * DATA_COL_W

    def row_y(i: int) -> float:
        """Bottom edge of data row i (0-indexed from top)."""
        return n - 1 - i  # header occupies n..n+1; row 0 occupies n-1..n

    # ── Header row ────────────────────────────────────────────────────────────
    header_y = n  # bottom of header row
    # Name-column header
    ax.add_patch(mpl.patches.Rectangle(
        (0, header_y), LABEL_COL_W, row_h,
        facecolor="#2c3e50", edgecolor="white", linewidth=0.5
    ))
    ax.text(LABEL_COL_W / 2, header_y + row_h / 2, "Agent",
            ha="center", va="center", fontsize=14, fontweight="bold", color="white")

    for j in range(n):
        ax.add_patch(mpl.patches.Rectangle(
            (col_x(j), header_y), DATA_COL_W, row_h,
            facecolor="#2c3e50", edgecolor="white", linewidth=0.5
        ))
        ax.text(col_x(j) + DATA_COL_W / 2, header_y + row_h / 2, str(j + 1),
                ha="center", va="center", fontsize=14, fontweight="bold", color="white")

    # Avg column header
    ax.add_patch(mpl.patches.Rectangle(
        (col_x(n), header_y), DATA_COL_W, row_h,
        facecolor="#1a252f", edgecolor="white", linewidth=0.5
    ))
    ax.text(col_x(n) + DATA_COL_W / 2, header_y + row_h / 2, "Avg",
            ha="center", va="center", fontsize=14, fontweight="bold", color="white")

    # ── Data rows ─────────────────────────────────────────────────────────────
    for i in range(n):
        y = row_y(i)
        rank = i + 1
        short_name = re.sub(r"-[0-9a-f]{7,8}$", "", agents[i]["name"])
        label = f"{rank}.  {short_name}"

        # Row-label cell
        row_bg = "#f0f0f0" if i % 2 == 0 else "#ffffff"
        ax.add_patch(mpl.patches.Rectangle(
            (0, y), LABEL_COL_W, row_h,
            facecolor=row_bg, edgecolor="#cccccc", linewidth=0.5
        ))
        ax.text(0.08, y + row_h / 2, label,
                ha="left", va="center", fontsize=11, color="#1a1a1a")

        for j in range(n):
            wr = wr_matrix[i, j]
            x = col_x(j)

            if i == j:
                facecolor = DIAG_COLOR
                text = "—"
                text_color = "#555555"
            elif np.isnan(wr):
                facecolor = NA_COLOR
                text = "n/a"
                text_color = NA_TEXT_COLOR
            else:
                facecolor = _win_rate_color(wr)
                text = f"{wr:.1f}%"
                # Dark text on mid tones, white on extremes
                luminance = 0.299 * facecolor[0] + 0.587 * facecolor[1] + 0.114 * facecolor[2]
                text_color = "#111111" if luminance > 0.45 else "#ffffff"

            ax.add_patch(mpl.patches.Rectangle(
                (x, y), DATA_COL_W, row_h,
                facecolor=facecolor, edgecolor="#cccccc", linewidth=0.5
            ))
            ax.text(x + DATA_COL_W / 2, y + row_h / 2, text,
                    ha="center", va="center", fontsize=10,
                    color=text_color, fontweight="bold" if not np.isnan(wr) and i != j else "normal")

        # Avg cell
        played = wr_matrix[i, ~np.isnan(wr_matrix[i, :])]
        avg_wr = played.mean() if played.size else np.nan
        avg_x = col_x(n)
        if np.isnan(avg_wr):
            avg_fc = NA_COLOR
            avg_text = "n/a"
            avg_tc = NA_TEXT_COLOR
        else:
            avg_fc = _win_rate_color(avg_wr)
            avg_text = f"{avg_wr:.1f}%"
            lum = 0.299 * avg_fc[0] + 0.587 * avg_fc[1] + 0.114 * avg_fc[2]
            avg_tc = "#111111" if lum > 0.45 else "#ffffff"
        ax.add_patch(mpl.patches.Rectangle(
            (avg_x, y), DATA_COL_W, row_h,
            facecolor=avg_fc, edgecolor="#888888", linewidth=1.0
        ))
        ax.text(avg_x + DATA_COL_W / 2, y + row_h / 2, avg_text,
                ha="center", va="center", fontsize=10, fontweight="bold", color=avg_tc)

    # ── Colorbar legend ───────────────────────────────────────────────────────
    cbar_ax = fig.add_axes([0.92, 0.15, 0.015, 0.7])
    sm = mpl.cm.ScalarMappable(cmap=CMAP, norm=mcolors.Normalize(vmin=0, vmax=100))
    sm.set_array([])
    cbar = fig.colorbar(sm, cax=cbar_ax)
    cbar.set_label("Win rate (%)", fontsize=12)
    cbar.set_ticks([0, 25, 50, 75, 100])

    fig.suptitle("CoG 2026 — Round-Robin Win Rates (row vs column)",
                 fontsize=17, fontweight="bold", y=0.98)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    generate()
