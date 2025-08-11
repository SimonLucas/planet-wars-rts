"""
PlanetWars Web Inspector
=========================

Single-file FastAPI app to browse your SQLite-backed PlanetWars league DB.

Features
- Leaderboard view (per league) using conservative score (mu - 3*sigma)
- List/search Agents
- Browse Leagues
- Browse Matches with filters & pagination
- Browse Ratings per league
- Minimal CSS (Pico.css CDN)

Run
----
1) Install deps:
   pip install fastapi uvicorn "sqlalchemy>=2" jinja2 pydantic

2) Ensure your models live in a `models.py` in the same folder, containing the ORM from your message
   (classes: Base, Agent, AgentInstance, League, Match, Rating). If your file is named differently,
   adjust the import below.

3) Set env var or edit DB_URL below to point to your SQLite file. Example:
   export PLANETWARS_DB=./planetwars_league.db

4) Start the server:
   uvicorn app:app --reload

Open http://127.0.0.1:8000

Notes
-----
- This is read-only. It never writes to the DB.
- Templates are written to ./templates/ at startup if they don't exist.
- Sorting & paging via query params. Simple, fast, dependency-light.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import create_engine, select, func, desc, asc
from sqlalchemy.orm import Session

from league.init_db import get_default_db_path

# ====== Import your SQLAlchemy ORM models ======
try:
    from league.league_schema import Base, Agent, AgentInstance, League, Match, Rating  # type: ignore
except Exception as e:  # pragma: no cover
    raise SystemExit(
        "\nCould not import models. Ensure a models.py (with your ORM classes) is next to this file.\n"
        f"Import error: {e}\n"
    )

# ====== Config ======
DB_URL = get_default_db_path()
engine = create_engine(DB_URL, future=True)

# ====== App & Templates ======
app = FastAPI(title="PlanetWars Web Inspector", version="1.0")

TEMPLATES_DIR = Path(__file__).parent / "templates"
TEMPLATES_DIR.mkdir(exist_ok=True)
# ====== App & Templates ======
app = FastAPI(title="PlanetWars Web Inspector", version="1.0")

TEMPLATES_DIR = Path(__file__).parent / "templates"
TEMPLATES_DIR.mkdir(exist_ok=True)

# Write minimal templates if not present
_base_html = """<!doctype html>
<html lang=\"en\">\n<head>\n  <meta charset=\"utf-8\">\n  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n  <title>{{ title or 'PlanetWars' }}</title>\n  <link rel=\"stylesheet\" href=\"https://unpkg.com/@picocss/pico@2/css/pico.min.css\">\n  <style>\n  .container { max-width: 1200px; }\n  table { font-size: 0.95rem; }\n  .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, \"Liberation Mono\", monospace; }\n  .nowrap { white-space: nowrap; }\n  .muted { opacity: .75; }\n  .grid { display: grid; gap: 1rem; }\n  .grid-cols-2 { grid-template-columns: 1fr 1fr; }\n  .grid-cols-3 { grid-template-columns: 1fr 1fr 1fr; }\n  </style>\n</head>\n<body>\n  <nav class=\"container\">\n    <ul>\n      <li><strong><a href=\"/\">PlanetWars DB</a></strong></li>\n    </ul>\n    <ul>\n      <li><a href=\"/leaderboard\">Leaderboard</a></li>\n      <li><a href=\"/agents\">Agents</a></li>\n      <li><a href=\"/matches\">Matches</a></li>\n      <li><a href=\"/leagues\">Leagues</a></li>\n      <li><a href=\"/ratings\">Ratings</a></li>\n    </ul>\n  </nav>\n  <main class=\"container\">\n    {% block content %}{% endblock %}\n  </main>\n</body>\n</html>"""

_index_html = """{% extends 'base.html' %}
{% block content %}
<h1>PlanetWars Web Inspector</h1>
<p class=\"muted\">Read-only browser for your SQLite-backed league database.</p>
<div class=\"grid grid-cols-3\">\n  <article>\n    <h3>Leaderboard</h3>\n    <p>Conservative score (mu − 3σ) per league.</p>\n    <a role=\"button\" href=\"/leaderboard\">View</a>\n  </article>\n  <article>\n    <h3>Agents</h3>\n    <p>Search by name/owner. Inspect repos and commits.</p>\n    <a role=\"button\" href=\"/agents\">Browse</a>\n  </article>\n  <article>\n    <h3>Matches</h3>\n    <p>Filter by league and agent, sort & paginate.</p>\n    <a role=\"button\" href=\"/matches\">Browse</a>\n  </article>\n</div>
{% endblock %}"""

_leaderboard_html = """{% extends 'base.html' %}
{% block content %}
<h2>Leaderboard</h2>
<form method=\"get\" class=\"grid grid-cols-3\">\n  <label>League\n    <select name=\"league_id\" onchange=\"this.form.submit()\">\n      {% for lg in leagues %}\n      <option value=\"{{ lg.league_id }}\" {% if lg.league_id == league_id %}selected{% endif %}>{{ lg.name }}</option>\n      {% endfor %}\n    </select>\n  </label>\n  <label>Limit\n    <input type=\"number\" name=\"limit\" value=\"{{ limit }}\" min=\"1\">\n  </label>\n  <div style=\"align-self:end\"><button type=\"submit\">Apply</button></div>\n</form>
<table role=\"grid\">\n  <thead><tr>\n    <th>#</th><th>Agent</th><th>Owner</th><th>μ</th><th>σ</th><th class=\"nowrap\">μ − 3σ</th><th>Updated</th>\n  </tr></thead>\n  <tbody>\n    {% for row in rows %}\n    <tr>\n      <td>{{ loop.index }}</td>\n      <td><a href=\"/agents?agent_id={{ row.agent_id }}\">{{ row.name }}</a></td>\n      <td class=\"mono\">{{ row.owner }}</td>\n      <td>{{ '%.3f'|format(row.mu) }}</td>\n      <td>{{ '%.3f'|format(row.sigma) }}</td>\n      <td>{{ '%.3f'|format(row.cs) }}</td>\n      <td class=\"nowrap\">{{ row.updated_at.strftime('%Y-%m-%d %H:%M') if row.updated_at else '' }}</td>\n    </tr>\n    {% endfor %}\n  </tbody>\n</table>
{% if not rows %}<p class=\"muted\">No ratings found for this league.</p>{% endif %}
{% endblock %}"""

_agents_html = """{% extends 'base.html' %}
{% block content %}
<h2>Agents</h2>
<form method=\"get\" class=\"grid grid-cols-3\">\n  <label>Search (name or owner)\n    <input type=\"text\" name=\"q\" value=\"{{ q or '' }}\" placeholder=\"e.g. gnn\">\n  </label>\n  <label>Agent ID\n    <input type=\"number\" name=\"agent_id\" value=\"{{ agent_id or '' }}\">\n  </label>\n  <div style=\"align-self:end\"><button type=\"submit\">Search</button></div>\n</form>
<table role=\"grid\">\n  <thead><tr>\n    <th>ID</th><th>Name</th><th>Owner</th><th>Repo</th><th>Commit</th><th>Created</th>\n  </tr></thead>\n  <tbody>\n    {% for a in agents %}\n    <tr>\n      <td>{{ a.agent_id }}</td>\n      <td class=\"mono\">{{ a.name }}</td>\n      <td>{{ a.owner }}</td>\n      <td class=\"mono\"><a href=\"{{ a.repo_url }}\" target=\"_blank\">repo</a></td>\n      <td class=\"mono\">{{ (a.commit or '')[:12] }}</td>\n      <td class=\"nowrap\">{{ a.created_at.strftime('%Y-%m-%d %H:%M') }}</td>\n    </tr>\n    {% endfor %}\n  </tbody>\n</table>
{% if not agents %}<p class=\"muted\">No agents match your query.</p>{% endif %}
{% endblock %}"""

_matches_html = """{% extends 'base.html' %}
{% block content %}
<h2>Matches</h2>
<form method=\"get\" class=\"grid grid-cols-3\">\n  <label>League\n    <select name=\"league_id\" onchange=\"this.form.submit()\">\n      <option value=\"\">All</option>\n      {% for lg in leagues %}\n      <option value=\"{{ lg.league_id }}\" {% if league_id and lg.league_id == league_id %}selected{% endif %}>{{ lg.name }}</option>\n      {% endfor %}\n    </select>\n  </label>\n  <label>Agent ID\n    <input type=\"number\" name=\"agent_id\" value=\"{{ agent_id or '' }}\">\n  </label>\n  <label>Page Size\n    <input type=\"number\" name=\"limit\" value=\"{{ limit }}\" min=\"5\" max=\"200\">\n  </label>\n  <label>Page\n    <input type=\"number\" name=\"page\" value=\"{{ page }}\" min=\"1\">\n  </label>\n  <div style=\"align-self:end\"><button type=\"submit\">Apply</button></div>\n</form>
<table role=\"grid\">\n  <thead><tr>\n    <th>ID</th><th>League</th><th>P1</th><th>P2</th><th>Winner</th><th>Seed</th><th>Map</th><th>Started</th><th>Finished</th>\n  </tr></thead>\n  <tbody>\n    {% for m in matches %}\n    <tr>\n      <td>{{ m.match_id }}</td>\n      <td>{{ m.league.name if m.league else m.league_id }}</td>\n      <td class=\"mono\"><a href=\"/agents?agent_id={{ m.player1_id }}\">{{ m.player1.name if m.player1 else m.player1_id }}</a></td>\n      <td class=\"mono\"><a href=\"/agents?agent_id={{ m.player2_id }}\">{{ m.player2.name if m.player2 else m.player2_id }}</a></td>\n      <td class=\"mono\">{{ m.winner.name if m.winner else m.winner_id }}</td>\n      <td>{{ m.seed }}</td>\n      <td class=\"mono\">{{ m.map_name }}</td>\n      <td class=\"nowrap\">{{ m.started_at.strftime('%Y-%m-%d %H:%M') if m.started_at else '' }}</td>\n      <td class=\"nowrap\">{{ m.finished_at.strftime('%Y-%m-%d %H:%M') if m.finished_at else '' }}</td>\n    </tr>\n    {% endfor %}\n  </tbody>\n</table>
{% if not matches %}<p class=\"muted\">No matches found.</p>{% endif %}
{% endblock %}"""

_leagues_html = """{% extends 'base.html' %}
{% block content %}
<h2>Leagues</h2>
<table role=\"grid\">\n  <thead><tr>\n    <th>ID</th><th>Name</th><th>Description</th><th>Created</th>\n  </tr></thead>\n  <tbody>\n    {% for l in leagues %}\n    <tr>\n      <td>{{ l.league_id }}</td>\n      <td class=\"mono\">{{ l.name }}</td>\n      <td>{{ l.description }}</td>\n      <td class=\"nowrap\">{{ l.created_at.strftime('%Y-%m-%d %H:%M') }}</td>\n    </tr>\n    {% endfor %}\n  </tbody>\n</table>
{% if not leagues %}<p class=\"muted\">No leagues yet.</p>{% endif %}
{% endblock %}"""

_ratings_html = """{% extends 'base.html' %}
{% block content %}
<h2>Ratings</h2>
<form method=\"get\" class=\"grid grid-cols-3\">\n  <label>League\n    <select name=\"league_id\" onchange=\"this.form.submit()\">\n      {% for lg in leagues %}\n      <option value=\"{{ lg.league_id }}\" {% if lg.league_id == league_id %}selected{% endif %}>{{ lg.name }}</option>\n      {% endfor %}\n    </select>\n  </label>\n  <div style=\"align-self:end\"><button type=\"submit\">Apply</button></div>\n</form>
<table role=\"grid\">\n  <thead><tr>\n    <th>Agent</th><th>μ</th><th>σ</th><th>Updated</th>\n  </tr></thead>\n  <tbody>\n    {% for r in ratings %}\n    <tr>\n      <td class=\"mono\">{{ r.agent.name if r.agent else r.agent_id }}</td>\n      <td>{{ '%.3f'|format(r.mu) }}</td>\n      <td>{{ '%.3f'|format(r.sigma) }}</td>\n      <td class=\"nowrap\">{{ r.updated_at.strftime('%Y-%m-%d %H:%M') if r.updated_at else '' }}</td>\n    </tr>\n    {% endfor %}\n  </tbody>\n</table>
{% if not ratings %}<p class=\"muted\">No ratings found for this league.</p>{% endif %}
{% endblock %}"""

# Write files if missing
_templates = {
    "base.html": _base_html,
    "index.html": _index_html,
    "leaderboard.html": _leaderboard_html,
    "agents.html": _agents_html,
    "matches.html": _matches_html,
    "leagues.html": _leagues_html,
    "ratings.html": _ratings_html,
}
for name, content in _templates.items():
    p = TEMPLATES_DIR / name
    if not p.exists():
        p.write_text(content, encoding="utf-8")

env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)

def render(template: str, **ctx: Any) -> HTMLResponse:
    t = env.get_template(template)
    return HTMLResponse(t.render(**ctx))

# ====== Helpers ======

def get_session() -> Session:
    return Session(engine, future=True)


def get_leagues(session: Session) -> List[League]:
    return list(session.scalars(select(League).order_by(desc(League.created_at))))


def get_default_league_id(session: Session) -> Optional[int]:
    lg = session.scalar(select(League).order_by(desc(League.created_at)).limit(1))
    return lg.league_id if lg else None

# ====== Routes ======
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    with get_session() as s:
        return render("index.html", title="PlanetWars DB")


@app.get("/leaderboard", response_class=HTMLResponse)
def leaderboard(
    request: Request,
    league_id: Optional[int] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=10000),
):
    with get_session() as s:
        leagues = get_leagues(s)
        if not leagues:
            return render("leaderboard.html", title="Leaderboard", leagues=[], league_id=None, rows=[], limit=limit)
        if league_id is None:
            league_id = get_default_league_id(s)
        # Join ratings with agent and compute conservative score
        from sqlalchemy import literal
        stmt = (
            select(
                Agent.agent_id,
                Agent.name,
                Agent.owner,
                Rating.mu,
                Rating.sigma,
                (Rating.mu - 3 * Rating.sigma).label("cs"),
                Rating.updated_at,
            )
            .join(Rating, Rating.agent_id == Agent.agent_id)
            .where(Rating.league_id == league_id)
            .order_by(desc("cs"))
            .limit(limit)
        )
        rows = [
            {
                "agent_id": r.agent_id,
                "name": r.name,
                "owner": r.owner,
                "mu": float(r.mu),
                "sigma": float(r.sigma),
                "cs": float(r.cs),
                "updated_at": r.updated_at,
            }
            for r in s.execute(stmt)
        ]
        return render("leaderboard.html", title="Leaderboard", leagues=leagues, league_id=league_id, rows=rows, limit=limit)


@app.get("/agents", response_class=HTMLResponse)
def list_agents(
    request: Request,
    q: Optional[str] = None,
    agent_id: Optional[int] = None,
):
    with get_session() as s:
        stmt = select(Agent)
        if agent_id is not None:
            stmt = stmt.where(Agent.agent_id == agent_id)
        if q:
            like = f"%{q}%"
            stmt = stmt.where((Agent.name.ilike(like)) | (Agent.owner.ilike(like)))
        stmt = stmt.order_by(asc(Agent.agent_id)).limit(1000)
        agents = list(s.scalars(stmt))
        return render("agents.html", title="Agents", agents=agents, q=q, agent_id=agent_id)


@app.get("/matches", response_class=HTMLResponse)
def list_matches(
    request: Request,
    league_id: Optional[int] = None,
    agent_id: Optional[int] = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=5, le=200),
):
    offset = (page - 1) * limit
    with get_session() as s:
        leagues = get_leagues(s)
        stmt = select(Match).order_by(desc(Match.match_id))
        if league_id is not None:
            stmt = stmt.where(Match.league_id == league_id)
        if agent_id is not None:
            stmt = stmt.where((Match.player1_id == agent_id) | (Match.player2_id == agent_id))
        stmt = stmt.limit(limit).offset(offset)
        matches = list(s.scalars(stmt))
        return render(
            "matches.html",
            title="Matches",
            matches=matches,
            leagues=leagues,
            league_id=league_id,
            agent_id=agent_id,
            page=page,
            limit=limit,
        )


@app.get("/leagues", response_class=HTMLResponse)
def list_leagues(request: Request):
    with get_session() as s:
        leagues = get_leagues(s)
        return render("leagues.html", title="Leagues", leagues=leagues)


@app.get("/ratings", response_class=HTMLResponse)
def list_ratings(
    request: Request,
    league_id: Optional[int] = None,
):
    with get_session() as s:
        leagues = get_leagues(s)
        if not leagues:
            return render("ratings.html", title="Ratings", leagues=[], league_id=None, ratings=[])
        if league_id is None:
            league_id = get_default_league_id(s)
        stmt = (
            select(Rating)
            .where(Rating.league_id == league_id)
            .order_by(desc(Rating.mu - 3 * Rating.sigma))
            .limit(1000)
        )
        ratings = list(s.scalars(stmt))
        return render("ratings.html", title="Ratings", leagues=leagues, league_id=league_id, ratings=ratings)


# Redirect handy short path
@app.get("/lb")
def goto_lb():
    return RedirectResponse("/leaderboard")
