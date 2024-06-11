from enums import Liga, GameType
from exceptions import RatingException
from datetime import datetime
from math import floor
import pandas as pd
import dataframe_image as dfi
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from difflib import get_close_matches
from models import Base, Player, Rating, Game, JSONGame
from typing import List
from constants import (
    date_format,
    BASIS_POINTS,
    RATING_MULTIPLIER,
    RATING_FACTOR,
    K_FACTOR,
    WIN_POINTS,
    MAX_RATING,
    MIN_RATING,
)
import logging
from typ import json
from os import environ, path, makedirs
import psycopg2


class RatingSystem:
    def __init__(self):
        username = environ["SUPABASE_USER"]
        password = environ["SUPABASE_PASSWORD"]
        host = environ["SUPABASE_HOST"]
        port = environ["SUPABASE_PORT"]
        dbname = environ["SUPABASE_NAME"]
        self.engine = create_engine(
            f"postgresql+psycopg2://{username}:{password}@{host}:{port}/{dbname}"
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()
        self.logger = logging.getLogger(__name__)

        # Setup logging
        if not path.exists("logs"):
            makedirs("logs")

        logging.basicConfig(
            level=logging.DEBUG,
            filename="logs/database.log",
            filemode="a",
            format="%(asctime)s %(levelname)s %(message)s",
            force=True,
        )

    def get_names(self):
        names = self.session.query(Player.name).all()
        self.logger.debug("Fetched all names from the database.")
        return [row[0] for row in names]

    def find_closest_name(self, name) -> str:
        matches = get_close_matches(name, self.get_names(), n=1, cutoff=0.3)
        if matches:
            return matches[0]
        else:
            self.logger.critical(
                f"Name {name} konnte nicht in der Datenbank gefunden werden."
            )
            raise NameError(
                f"Name {name} konnte nicht in der Datenbank gefunden werden. Bitte überprüfe die Eingabe."
            )

    def add_player(
        self,
        name: str,
        phone_number: str,
        country: str = "Deutschland",
        liga: Liga = Liga.KEINE,
    ) -> str:
        existing_player = self.session.query(Player).filter_by(name=name).first()
        if existing_player:
            self.logger.debug(f"Player {name} already exists in the database.")
            raise RatingException(f"Spieler {name} bereits in der Datenbank vorhanden.")

        new_player = Player(
            name=name, country=country, phone_number=phone_number, liga=liga
        )
        self.session.add(new_player)
        self.session.commit()
        self.logger.info(f"Added new player {name} to the database.")

    def add_player_to_rating(self, name: str):
        player = self.session.query(Player).filter_by(name=name).first()

        if not player:
            raise RatingException(f"Player {name} not found in the database.")

        existing_rating = (
            self.session.query(Rating).filter_by(player_id=player.id).first()
        )

        if existing_rating:
            self.logger.debug(
                f"Rating for player {name} already exists in the database."
            )
            return

        new_rating = Rating(
            player_id=player.id,
            rating=BASIS_POINTS,
            games_won=0,
            games_lost=0,
            last_change=datetime.now().strftime(date_format),
        )

        self.session.add(new_rating)
        self.session.commit()
        self.logger.info(f"Added player {name} to rating.")

    def add_games(self, player1, player2, scores, game_type: GameType):
        for score1, score2 in scores:
            self.add_game(player1, player2, score1, score2, game_type)

    def add_game(self, playerA_name, playerB_name, scoreA, scoreB, game_type: GameType):
        """
        Adds a new game to the database.

        Args:
            playerA_name (str): The name of player A.
            playerB_name (str): The name of player B.
            scoreA (int): The score of player A.
            scoreB (int): The score of player B.
            game_type (GameType): The type of the game.

        Raises:
            RatingException: If player A or player B is not found in the database.

        Returns:
            None
        """

        playerA = self.session.query(Player).filter_by(name=playerA_name).first()
        playerB = self.session.query(Player).filter_by(name=playerB_name).first()

        if not playerA:
            raise RatingException(f"Player {playerA_name} not found in the database.")
        if not playerB:
            raise RatingException(f"Player {playerB_name} not found in the database.")

        new_game = Game(
            playerA_id=playerA.id,
            playerB_id=playerB.id,
            scoreA=scoreA,
            scoreB=scoreB,
            race_to=game_type.value,
            disciplin=game_type.name,
        )
        self.session.add(new_game)
        self.session.commit()
        self.logger.info(f"Added new game between {playerA_name} and {playerB_name}.")

    def delete_game(self, game_id: int):
        if not self.session.query(Game).filter_by(id=game_id).first():
            raise RatingException(f"Game with ID {game_id} not found in the database.")
        else:
            self.session.query(Game).filter_by(id=game_id).delete()
            self.session.commit()
            self.logger.info(f"Deleted game with ID {game_id}.")

    def update_ratings(self, player1, player2, scores, game_type):
        for score1, score2 in scores:
            newRating1, newRating2 = self.update_rating(
                player1, player2, score1, score2, game_type
            )
        return newRating1, newRating2

    def update_rating(
        self,
        playerA_name: str,
        playerB_name: str,
        scoreA: float,
        scoreB: float,
        game_type: GameType,
    ):
        playerA = self.session.query(Player).filter_by(name=playerA_name).first()
        playerB = self.session.query(Player).filter_by(name=playerB_name).first()

        if not playerA or not playerB:
            raise RatingException("One or both players not found in the database.")

        playerA_rating = (
            self.session.query(Rating).filter_by(player_id=playerA.id).first()
        )
        playerB_rating = (
            self.session.query(Rating).filter_by(player_id=playerB.id).first()
        )

        if not playerA_rating:
            raise RatingException(f"Player {playerA_name} not found in the rating.")
        if not playerB_rating:
            raise RatingException(f"Player {playerB_name} not found in the rating.")

        # Calculate the change in rating
        calc_element = 1 / (
            1 + pow(10, ((playerA_rating - playerB_rating) / RATING_FACTOR))
        )

        if game_type == GameType.NORMAL:
            rating_change = K_FACTOR * (scoreA - calc_element * (scoreA + scoreB))

            self.logger.info(
                f"Normal game: rating change is {rating_change}.\nPlayer {playerA_name} won {scoreA} games, player {playerB_name} won {scoreB} games."
            )
        else:
            scoreFactor1 = (
                scoreB / 10.0
                if scoreA > scoreB
                else floor(scoreA / scoreB * scoreA / 10.0)
            )
            scoreFactor2 = (
                floor(scoreB / scoreA * scoreB / 10.0)
                if scoreB < scoreA
                else scoreA / 10.0
            )

            rating_change = K_FACTOR * (
                scoreFactor1 - calc_element * (scoreFactor1 + scoreFactor2)
            )

            self.logger.info(
                f"14.1 game: rating change is {rating_change}.\nPlayer {playerA_name} won {scoreA} games, player {playerB_name} won {scoreB} games.\nThe score factors are {scoreFactor1} and {scoreFactor2}."
            )

        # Update the ratings
        playerA_rating.rating += rating_change
        playerB_rating.rating -= rating_change

        # Update the last_changed date
        playerA_rating.last_change = datetime.now().strftime(date_format)
        playerB_rating.last_change = datetime.now().strftime(date_format)

        # Update the games won and lost
        playerA_rating.games_won += scoreA
        playerA_rating.games_lost += scoreB

        playerB_rating.games_won += scoreB
        playerB_rating.games_lost += scoreA

        self.session.commit()
        self.logger.info(
            f"Updated ratings for players {playerA_name} and {playerB_name}."
        )

    def process_games(self):
        with open("games.json", "r+") as file:
            games: List[JSONGame] = json.load(file, List[JSONGame])

            for game in games:
                self.update_rating(
                    game.playerA, game.playerB, game.scoreA, game.scoreB, game.disciplin
                )
                self.session.add(game)
            self.session.commit()
            file.seek(0)
            file.truncate()
            json.dump([], file)

    def rating_image(self):
        query = self.session.query(Rating).order_by(Rating.rating.desc()).all()
        data = pd.DataFrame(
            [
                (
                    r.player_id,
                    r.rating,
                    r.winning_quote,
                    r.games_won,
                    r.games_lost,
                    r.last_change,
                )
                for r in query
            ],
            columns=[
                "Player ID",
                "Rating",
                "Winning Quote",
                "Games Won",
                "Games Lost",
                "Last Change",
            ],
        )
        data.index = range(1, len(data) + 1)
        data["Rating"] = data["Rating"].astype(int)

        dfi.export(data, "./RatingImage.png")
        self.logger.info("Exported the rating table as an image.")
