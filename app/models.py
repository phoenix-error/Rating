from sqlalchemy import Column, Integer, String, ForeignKey, Float, Date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from dataclasses import dataclass

Base = declarative_base()


class Player(Base):
    __tablename__ = "players"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    phone_number = Column(String, nullable=False, unique=True)
    country = Column(String, nullable=False)

    games = relationship(
        "Game", primaryjoin="or_(Player.id==Game.playerA, Player.id==Game.playerB)"
    )


class Rating(Base):
    __tablename__ = "ratings"
    player = Column(Integer, ForeignKey("players.id"), primary_key=True)
    rating = Column(Float, nullable=False)
    winning_quote = Column(Float, nullable=True)
    games_won = Column(Integer, nullable=False, default=0)
    games_lost = Column(Integer, nullable=False, default=0)
    last_change = Column(Date, nullable=False)


class Game(Base):
    __tablename__ = "games"
    id = Column(Integer, primary_key=True)
    playerA = Column(Integer, ForeignKey("players.id"))
    playerB = Column(Integer, ForeignKey("players.id"))
    scoreA = Column(Integer, nullable=False)
    scoreB = Column(Integer, nullable=False)
    race_to = Column(Integer, nullable=False)
    disciplin = Column(String, nullable=False)


@dataclass
class JSONGame:
    id: int
    playerA: int
    playerB: int
    scoreA: int
    scoreB: int
    race_to: int
    disciplin: str
