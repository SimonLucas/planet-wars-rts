from sqlalchemy import (
    create_engine, Integer, String, Float, Text, ForeignKey, DateTime, JSON, func
)
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column
from datetime import datetime


class Base(DeclarativeBase):
    pass


from sqlalchemy import UniqueConstraint


class Agent(Base):
    __tablename__ = "agent"

    agent_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    owner: Mapped[str] = mapped_column(String)
    repo_url: Mapped[str] = mapped_column(String)
    commit: Mapped[str] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    ratings = relationship("Rating", back_populates="agent")
    instance = relationship("AgentInstance", back_populates="agent", uselist=False)

    __table_args__ = (
        UniqueConstraint("name", "commit", name="uix_name_commit"),
    )


class AgentInstance(Base):
    __tablename__ = "agent_instance"

    agent_id: Mapped[int] = mapped_column(ForeignKey("agent.agent_id"), primary_key=True)
    port: Mapped[int] = mapped_column(Integer)
    container_id: Mapped[str] = mapped_column(String)
    last_seen: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    agent = relationship("Agent", back_populates="instance")


class League(Base):
    __tablename__ = "league"

    league_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    settings: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    matches = relationship("Match", back_populates="league")
    ratings = relationship("Rating", back_populates="league")  # ✅ if needed


class Match(Base):
    __tablename__ = "match"

    match_id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("league.league_id"))
    player1_id: Mapped[int] = mapped_column(ForeignKey("agent.agent_id"))
    player2_id: Mapped[int] = mapped_column(ForeignKey("agent.agent_id"))

    map_name: Mapped[str] = mapped_column(String)
    seed: Mapped[int] = mapped_column(Integer)
    game_params: Mapped[dict] = mapped_column(JSON)

    started_at: Mapped[datetime] = mapped_column(nullable=True)
    finished_at: Mapped[datetime] = mapped_column(nullable=True)

    winner_id: Mapped[int] = mapped_column(ForeignKey("agent.agent_id"))
    player1_score: Mapped[int] = mapped_column(Integer)
    player2_score: Mapped[int] = mapped_column(Integer)
    log_url: Mapped[str] = mapped_column(String)

    league = relationship("League", back_populates="matches")
    player1 = relationship("Agent", foreign_keys=[player1_id])
    player2 = relationship("Agent", foreign_keys=[player2_id])
    winner = relationship("Agent", foreign_keys=[winner_id])


class Rating(Base):
    __tablename__ = "rating"

    agent_id: Mapped[int] = mapped_column(ForeignKey("agent.agent_id"), primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("league.league_id"), primary_key=True)
    mu: Mapped[float] = mapped_column(Float)
    sigma: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    agent = relationship("Agent", back_populates="ratings")
    league = relationship("League", back_populates="ratings")
