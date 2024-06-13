from sqlalchemy import Column, Integer, String, ForeignKey, Float, Date, UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, backref
import uuid
import random
from datetime import datetime
from enums import Liga

Base = declarative_base()


class Player(Base):
    __tablename__ = "players"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    phone_number = Column(String, nullable=False, unique=True)
    country = Column(String, nullable=False)
    liga = Column(String, nullable=False, default=Liga.KEINE.value)

    games = relationship("Game", primaryjoin="or_(Player.id==Game.playerA, Player.id==Game.playerB)")


class Rating(Base):
    __tablename__ = "ratings"
    player = Column(UUID, ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    rating = Column(Float, nullable=False)
    winning_quote = Column(Float, nullable=True)
    games_won = Column(Integer, nullable=False, default=0)
    games_lost = Column(Integer, nullable=False, default=0)
    last_change = Column(Date, nullable=False, onupdate=datetime.now)


class Game(Base):
    __tablename__ = "games"
    id = Column(String, primary_key=True)
    playerA = Column(UUID, ForeignKey("players.id"))
    playerB = Column(UUID, ForeignKey("players.id"))
    scoreA = Column(Integer, nullable=False)
    scoreB = Column(Integer, nullable=False)
    race_to = Column(Integer, nullable=False)
    disciplin = Column(String, nullable=False)
    rating_change = Column(Float, nullable=False)

    @staticmethod
    def generate_unique_id(session):
        while True:
            game_id = f"#{random.randint(0, 999999):06}"
            if not session.query(Game).filter_by(id=game_id).first():
                return game_id

    def __init__(self, playerA, playerB, scoreA, scoreB, race_to, disciplin, rating_change, session):
        self.id = Game.generate_unique_id(session)
        self.playerA = playerA
        self.playerB = playerB
        self.scoreA = scoreA
        self.scoreB = scoreB
        self.race_to = race_to
        self.disciplin = disciplin
        self.rating_change = rating_change
