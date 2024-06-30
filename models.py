import logging
from datetime import datetime
from math import floor
from random import randint
from uuid import uuid4

from sqlalchemy import UUID, Column, Date, Float, ForeignKey, Integer, String
from sqlalchemy.orm import declarative_base, relationship

from utils.enums import GameType
from utils.exceptions import GameTypeNotSupportedException

RATING_FACTOR = 120
K_FACTOR = 1.2

Base = declarative_base()


class Player(Base):
    __tablename__ = "players"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, nullable=False)
    phone_number = Column(String, nullable=False, unique=True)

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
    created_at = Column(Date, nullable=False, default=datetime.now)

    @staticmethod
    def generate_unique_id(session):
        while True:
            game_id = f"#{randint(0, 999999):06}"
            if not session.query(Game).filter_by(id=game_id).first():
                return game_id

    def __init__(self, playerA, playerB, scoreA, scoreB, race_to, disciplin, session):
        self.id = Game.generate_unique_id(session)
        self.playerA = playerA
        self.playerB = playerB
        self.scoreA = scoreA
        self.scoreB = scoreB
        self.race_to = race_to
        self.disciplin = disciplin.strip()
        self.created_at = datetime.now()
        self.rating_change = self.calculate_rating(session)

    def calculate_rating(self, session) -> float:
        playerA_rating = session.query(Rating).filter_by(player=self.playerA).first().rating
        playerB_rating = session.query(Rating).filter_by(player=self.playerB).first().rating

        playerA = session.query(Player).filter_by(id=self.playerA).first()
        playerB = session.query(Player).filter_by(id=self.playerB).first()

        calc_element = 1 / (1 + pow(10, ((playerB_rating - playerA_rating) / RATING_FACTOR)))

        logging.info("GameType: " + self.disciplin)

        if self.disciplin.lower() == "normal":
            rating_change = K_FACTOR * (self.scoreA - calc_element * (self.scoreA + self.scoreB))
            logging.info(
                f"Normales Spiel: Rating-Änderung beträgt {rating_change}.\nSpieler {playerA.name} hat {self.scoreA} Spiele gewonnen, Spieler {playerB.name} hat {self.scoreB} Spiele gewonnen."
            )
        elif self.disciplin == "14.1":
            scoreFactor1 = (
                self.scoreB / 10.0 if self.coreA > self.scoreB else floor(self.scoreA / self.scoreB * self.scoreA / 10.0)
            )
            scoreFactor2 = (
                floor(self.scoreB / self.scoreA * self.scoreB / 10.0) if self.scoreB < self.scoreA else self.scoreA / 10.0
            )

            rating_change = K_FACTOR * (scoreFactor1 - calc_element * (scoreFactor1 + scoreFactor2))
            logging.info(
                f"14.1 Spiel: Rating-Änderung beträgt {rating_change}.\nSpieler {playerA.name} hat {self.scoreA} Spiele gewonnen, Spieler {playerB.name} hat {self.scoreB} Spiele gewonnen.\nDie Score-Faktoren sind {scoreFactor1} und {scoreFactor2}."
            )
        else:
            raise GameTypeNotSupportedException(self.disciplin)

        return rating_change

    def adjust_ratings(self, session):
        try:
            ratingA = session.query(Rating).filter_by(player=self.playerA).first()
            ratingB = session.query(Rating).filter_by(player=self.playerB).first()

            playerA = session.query(Player).filter_by(id=self.playerA).first()
            playerB = session.query(Player).filter_by(id=self.playerB).first()

            ratingA.games_won += self.scoreA
            ratingA.games_lost += self.scoreB
            ratingB.games_won += self.scoreB
            ratingB.games_lost += self.scoreA

            ratingA.rating += self.rating_change
            ratingB.rating -= self.rating_change

            if ratingA.games_won + ratingA.games_lost == 0:
                ratingA.winning_quote = None
            else:
                ratingA.winning_quote = ratingA.games_won / (ratingA.games_won + ratingA.games_lost)

            if ratingB.games_won + ratingB.games_lost == 0:
                ratingB.winning_quote = None
            else:
                ratingB.winning_quote = ratingB.games_won / (ratingB.games_won + ratingB.games_lost)

            ratingA.last_change = datetime.now()
            ratingB.last_change = datetime.now()

            logging.info(f"Rating für Spieler {playerA.name} und {playerB.name} aktualisiert.")

        except:
            session.rollback()
        else:
            session.commit()
