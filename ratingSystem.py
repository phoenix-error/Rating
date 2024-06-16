from enums import Liga, GameType
from exceptions import RatingException
from datetime import datetime
from math import floor
import pandas as pd
import dataframe_image as dfi
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from difflib import get_close_matches
from models import Base, Player, Rating, Game
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
from os import environ
from sqlalchemy.exc import NoResultFound
from supabase import create_client, Client
from dotenv import load_dotenv


class RatingSystem:
    def __init__(self):
        load_dotenv()
        username = environ["SUPABASE_USER"]
        password = environ["SUPABASE_PASSWORD"]
        host = environ["SUPABASE_HOST"]
        port = environ["SUPABASE_PORT"]
        dbname = environ["SUPABASE_NAME"]
        self.engine = create_engine(f"postgresql+psycopg2://{username}:{password}@{host}:{port}/{dbname}")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()
        self.logger = logging.getLogger(__name__)

        url: str = environ["SUPABASE_URL"]
        key: str = environ["SUPABASE_KEY"]
        self.supabase: Client = create_client(url, key)

        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s %(levelname)s %(message)s",
            force=True,
        )

    def get_names(self):
        names = self.session.query(Player.name).all()
        self.logger.debug("Alle Namen aus der Datenbank abgerufen.")
        return [row[0] for row in names]

    def find_closest_name(self, name) -> str:
        self.logger.info(f"Suche nach Namen {name} in der Datenbank.")
        matches = get_close_matches(name, self.get_names(), n=1, cutoff=0.3)
        if matches:
            return matches[0]
        else:
            self.logger.critical(f"Name {name} konnte nicht in der Datenbank gefunden werden.")
            raise NameError(f"Name {name} konnte nicht in der Datenbank gefunden werden. Bitte überprüfe die Eingabe.")

    def add_player(
        self,
        name: str,
        phone_number: str,
    ) -> str:
        existing_player = self.session.query(Player).filter_by(phone_number=phone_number).first()
        if existing_player:
            self.logger.debug(f"Spieler mit nummer {phone_number} bereits in der Datenbank vorhanden.")
            raise RatingException(f"Du bist bereits in der Datenbank vorhanden.")

        new_player = Player(name=name, phone_number=phone_number)
        self.session.add(new_player)
        self.session.commit()
        self.logger.info(f"Neuer Spieler {name} wurde zur Datenbank hinzugefügt.")

    def delete_player(self, phone_number: str):
        try:
            self.logger.debug(f"Suche {phone_number} in der Datenbank.")
            player = self.session.query(Player).filter_by(phone_number=phone_number).one()
            self.logger.debug(f"Spieler {player.name} in der Datenbank gefunden.")

            self.session.delete(player)
            self.session.commit()
            self.logger.info(f"Spielereintrag für {player.name} aus der Datenbank gelöscht.")
        except NoResultFound:
            raise RatingException(f"Du wurdest nicht in der Datenbank gefunden.\nWende dich an den Administrator.")

    def add_player_to_rating(self, phone_number: str):
        player = self.session.query(Player).filter_by(phone_number=phone_number).first()

        if not player:
            raise RatingException(
                f"Du wurdest nicht in der Datenbank gefunden.\nErstelle erst einen Spieler mit deiner Nummer.\nFür Hilfe schreibe dem Administrator."
            )

        existing_rating = self.session.query(Rating).filter_by(player=player.id).first()

        if existing_rating:
            self.logger.debug(f"Spieler {player.name} bereits im Rating.")
            return

        new_rating = Rating(
            player=player.id,
            rating=BASIS_POINTS,
            games_won=0,
            games_lost=0,
            last_change=datetime.now(),
        )

        self.session.add(new_rating)
        self.session.commit()
        self.logger.info(f"Spieler {player.name} zum Rating hinzugefügt.")

    def add_games(self, playerA, playerB, scores, game_type, phone_number) -> list[str]:
        ids = []
        for score1, score2 in scores:
            id = self.add_game(playerA, playerB, score1, score2, game_type, phone_number)
            ids.append(id)
        return ids

    def add_game(self, playerA_name, playerB_name, scoreA, scoreB, game_type, phone_number) -> str:
        """
        Adds a new game to the database.

        Args:
            playerA_name (str): The name of player A.
            playerB_name (str): The name of player B.
            scoreA (int): The score of player A.
            scoreB (int): The score of player B.
            game_type (str): The type of the game.
            phone_number (str): The phone number of the player adding the game.

        Raises:
            RatingException:

        Returns:
            str: The ID of the newly added game.
        """

        playerA_name = self.find_closest_name(playerA_name)
        playerB_name = self.find_closest_name(playerB_name)

        playerA = self.session.query(Player).filter_by(name=playerA_name).first()
        playerB = self.session.query(Player).filter_by(name=playerB_name).first()

        if not playerA and not playerB:
            raise RatingException(f"{playerA_name} und {playerB_name} nicht in der Datenbank gefunden.")
        elif not playerA:
            raise RatingException(f"{playerA_name} nicht in der Datenbank gefunden.")
        elif not playerB:
            raise RatingException(f"{playerB_name} nicht in der Datenbank gefunden.")

        # Check if the player adding the game is one of the players
        if playerA.phone_number != phone_number and playerB.phone_number != phone_number:
            raise RatingException(f"Du bist nicht einer der Spieler in diesem Spiel.")

        # Update ratings
        rating_change = self._update_rating(playerA, playerB, scoreA, scoreB, game_type)

        new_game = Game(
            playerA=playerA.id,
            playerB=playerB.id,
            scoreA=scoreA,
            scoreB=scoreB,
            race_to=max(scoreA, scoreB),
            disciplin=game_type,
            rating_change=rating_change,
            session=self.session,
        )
        self.session.add(new_game)
        self.session.commit()
        self.logger.info(f"Neues Spiel hinzugefügt (ID: {new_game.id}) zwischen {playerA_name} und {playerB_name}.")

        return str(new_game.id)

    def delete_game(self, game_id: int, phone_number: str):
        if not self.session.query(Game).filter_by(id=game_id).first():
            raise RatingException(f"Spiel mit ID {game_id} nicht in der Datenbank gefunden.")
        else:
            # Check if the player deleting the game is one of the players
            game = self.session.query(Game).filter_by(id=game_id).first()
            playerA = self.session.query(Player).filter_by(id=game.playerA).first()
            playerB = self.session.query(Player).filter_by(id=game.playerB).first()

            if (not playerA or playerA.phone_number != phone_number) and (not playerB or playerB.phone_number != phone_number):
                raise RatingException(f"Du bist nicht einer der Spieler in diesem Spiel.")

            self.session.query(Game).filter_by(id=game_id).delete()
            self.session.commit()
            self.logger.info(f"Spiel mit ID {game_id} gelöscht.")

    def _update_rating(
        self,
        playerA: Player,
        playerB: Player,
        scoreA: float,
        scoreB: float,
        game_type: GameType,
    ):
        playerA_rating = self.session.query(Rating).filter_by(player=playerA.id).first()
        playerB_rating = self.session.query(Rating).filter_by(player=playerB.id).first()

        if not playerA_rating and not playerB_rating:
            raise RatingException(f"{playerA.name} und {playerB.name} nicht im Rating gefunden.")
        elif not playerA_rating:
            raise RatingException(f"{playerA.name} nicht im Rating gefunden.")
        elif not playerB_rating:
            raise RatingException(f"{playerB.name} nicht im Rating gefunden.")

        # Calculate the change in rating
        calc_element = 1 / (1 + pow(10, ((playerA_rating.rating - playerB_rating.rating) / RATING_FACTOR)))

        if game_type == GameType.NORMAL.value:
            rating_change = K_FACTOR * (scoreA - calc_element * (scoreA + scoreB))

            self.logger.info(
                f"Normales Spiel: Rating-Änderung beträgt {rating_change}.\nSpieler {playerA.name} hat {scoreA} Spiele gewonnen, Spieler {playerB.name} hat {scoreB} Spiele gewonnen."
            )
        elif game_type == GameType.STRAIGHT.value:
            scoreFactor1 = scoreB / 10.0 if scoreA > scoreB else floor(scoreA / scoreB * scoreA / 10.0)
            scoreFactor2 = floor(scoreB / scoreA * scoreB / 10.0) if scoreB < scoreA else scoreA / 10.0

            rating_change = K_FACTOR * (scoreFactor1 - calc_element * (scoreFactor1 + scoreFactor2))

            self.logger.info(
                f"14.1 Spiel: Rating-Änderung beträgt {rating_change}.\nSpieler {playerA.name} hat {scoreA} Spiele gewonnen, Spieler {playerB.name} hat {scoreB} Spiele gewonnen.\nDie Score-Faktoren sind {scoreFactor1} und {scoreFactor2}."
            )
        else:
            raise RatingException(f"Spieltyp {game_type} wird nicht unterstützt.")

        # Update the ratings
        playerA_rating.rating += rating_change
        playerB_rating.rating -= rating_change

        # Update the last_changed date
        playerA_rating.last_change = datetime.now()
        playerB_rating.last_change = datetime.now()

        # Update the games won and lost
        playerA_rating.games_won += scoreA
        playerA_rating.games_lost += scoreB

        playerB_rating.games_won += scoreB
        playerB_rating.games_lost += scoreA

        self.logger.info(f"Bewertungen für Spieler {playerA.name} und {playerB.name} aktualisiert.")

        return rating_change

    def rating_image(self):
        row_number = func.row_number().over().label("Platz")
        rounded_rating = func.round(Rating.rating).label("Rating")
        query = (
            self.session.query(
                row_number,
                Player.name.label("Namen"),
                rounded_rating,
                Rating.winning_quote.label("Sieger Quote"),
                Rating.games_won.label("Spiele (G)"),
                Rating.games_lost.label("Spiele (V)"),
                Rating.last_change.label("Letze Änderung"),
            )
            .join(Rating, Player.id == Rating.player)
            .order_by(Player.id)
        )

        result = query.all()

        data = pd.DataFrame(result)
        dfi.export(data.style.hide(axis="index"), "./rating.png", table_conversion="selenium")

        try:
            storage = self.supabase.storage
            buckets = storage.list_buckets()
            if not buckets:
                storage.create_bucket("rating", options={"public": True})
                self.logger.info("Ein neuer Bucket für das Rating-Tabellenbild wurde erstellt.")

            ratingBucket = storage.from_("rating")

            with open("./rating.png", "rb") as f:
                storage.empty_bucket("rating")
                ratingBucket.upload(path="./rating.png", file=f, file_options={"content-type": "image/png"})

                res = ratingBucket.get_public_url("rating.png")
                self.logger.info("Das Rating-Tabellenbild wurde exportiert.")
                return res
        except Exception as e:
            self.logger.error(f"Fehler beim Hochladen des Bildes in den Speicher: {e}")
            return "Fehler beim Erstellen des Ratings. Bitte versuche es später erneut."
