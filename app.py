"""Initialize Flask app."""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from uuid import uuid4
from datetime import datetime
from random import randint
from utils.enums import GameType
import logging
from utils.constants import RATING_FACTOR, K_FACTOR
from math import floor
from utils.exceptions import GameTypeNotSupportedException


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


def create_app():
    """Construct the core application."""
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object("config.Config")

    db.init_app(app)

    with app.app_context():
        db.create_all()
        return app


app = create_app()


class Player(db.Model):
    __tablename__ = "players"
    id = db.Column(db.UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = db.Column(db.String, nullable=False)
    phone_number = db.Column(db.String, nullable=False, unique=True)

    games = db.relationship("Game", primaryjoin="or_(Player.id==Game.playerA, Player.id==Game.playerB)")


class Rating(db.Model):
    __tablename__ = "ratings"
    player = db.Column(db.UUID, db.ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    rating = db.Column(db.Float, nullable=False)
    winning_quote = db.Column(db.Float, nullable=True)
    games_won = db.Column(db.Integer, nullable=False, default=0)
    games_lost = db.Column(db.Integer, nullable=False, default=0)
    last_change = db.Column(db.Date, nullable=False, onupdate=datetime.now)


class Game(db.Model):
    __tablename__ = "games"
    id = db.Column(db.String, primary_key=True)
    playerA = db.Column(db.UUID, db.ForeignKey("players.id"))
    playerB = db.Column(db.UUID, db.ForeignKey("players.id"))
    scoreA = db.Column(db.Integer, nullable=False)
    scoreB = db.Column(db.Integer, nullable=False)
    race_to = db.Column(db.Integer, nullable=False)
    disciplin = db.Column(db.String, nullable=False)
    rating_change = db.Column(db.Float, nullable=False)

    @staticmethod
    def generate_unique_id():
        while True:
            game_id = f"#{randint(0, 999999):06}"
            if not db.session.query(Game).filter_by(id=game_id).first():
                return game_id

    def __init__(self, playerA, playerB, scoreA, scoreB, race_to, disciplin):
        self.id = Game.generate_unique_id()
        self.playerA = playerA
        self.playerB = playerB
        self.scoreA = scoreA
        self.scoreB = scoreB
        self.race_to = race_to
        self.disciplin = disciplin
        self.rating_change = self.calculate_rating()
        self.adjust_ratings()

    def calculate_rating(self) -> float:
        playerA_rating = db.session.query(Rating).filter_by(player=self.playerA).first().rating
        playerB_rating = db.session.query(Rating).filter_by(player=self.playerB).first().rating

        playerA = db.session.query(Player).filter_by(id=self.playerA).first()
        playerB = db.session.query(Player).filter_by(id=self.playerB).first()

        calc_element = 1 / (1 + pow(10, ((playerB_rating - playerA_rating) / RATING_FACTOR)))

        if self.disciplin == GameType.NORMAL.value:
            rating_change = K_FACTOR * (self.scoreA - calc_element * (self.scoreA + self.scoreB))
            logging.info(
                f"Normales Spiel: Rating-Änderung beträgt {rating_change}.\nSpieler {playerA.name} hat {self.scoreA} Spiele gewonnen, Spieler {playerB.name} hat {self.scoreB} Spiele gewonnen."
            )
        elif self.disciplin == GameType.STRAIGHT.value:
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
            raise GameTypeNotSupportedException()

        return rating_change

    def adjust_ratings(self):
        try:
            ratingA = db.session.query(Rating).filter_by(player=self.playerA).first()
            ratingB = db.session.query(Rating).filter_by(player=self.playerB).first()

            playerA = db.session.query(Player).filter_by(id=self.playerA).first()
            playerB = db.session.query(Player).filter_by(id=self.playerB).first()

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
            db.session.rollback()
        else:
            db.session.commit()
