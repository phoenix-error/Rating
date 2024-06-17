from enums import Liga, GameType
from exceptions import *
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
        return [row[0] for row in names]

    def find_closest_name(self, name) -> str:
        self.logger.info(f"Suche nach Namen {name} in der Datenbank.")
        matches = get_close_matches(name, self.get_names(), n=1, cutoff=0.3)
        if matches:
            return matches[0]
        else:
            self.logger.info(f"Name {name} konnte nicht in der Datenbank gefunden werden.")
            raise PlayerNotFoundException(name)

    def add_player(
        self,
        name: str,
        phone_number: str,
    ) -> str:
        existing_player = self.session.query(Player).filter_by(phone_number=phone_number).first()
        if existing_player:
            self.logger.debug(f"Spieler {existing_player.name} bereits in der Datenbank vorhanden.")
            raise PlayerAlreadyExistsException(existing_player.name)

        new_player = Player(name=name, phone_number=phone_number)

        self.session.add(new_player)
        self.session.commit()
        self.logger.info(f"Neuer Spieler {name} wurde zur Datenbank hinzugefügt.")

    def delete_player(self, phone_number: str):
        try:
            self.logger.info(f"Suche {phone_number} in der Datenbank.")
            player = self.session.query(Player).filter_by(phone_number=phone_number).one()
            self.logger.info(f"Spieler {player.name} in der Datenbank gefunden.")

            name = player.name

            self.session.delete(player)
            self.session.commit()
            self.logger.info(f"Spielereintrag für {player.name} aus der Datenbank gelöscht.")
            return name
        except NoResultFound:
            raise PlayerNotFoundException(f"mit Handynummer: {phone_number}")

    def add_player_to_rating(self, phone_number: str):
        player = self.session.query(Player).filter_by(phone_number=phone_number).first()

        if not player:
            raise PlayerNotFoundException(f"mit Handynummer: {phone_number}")

        existing_rating = self.session.query(Rating).filter_by(player=player.id).first()

        if existing_rating:
            self.logger.info(f"Spieler {player.name} bereits im Rating.")
            raise PlayerAlreadyInRatingException(player.name)

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
        playerA_name = self.find_closest_name(playerA_name)
        playerB_name = self.find_closest_name(playerB_name)

        playerA = self.session.query(Player).filter_by(name=playerA_name).first()
        playerB = self.session.query(Player).filter_by(name=playerB_name).first()

        if not playerA and not playerB:
            raise PlayerNotFoundException(playerA_name, playerB_name)
        elif not playerA:
            raise PlayerNotFoundException(playerA_name)
        elif not playerB:
            raise PlayerNotFoundException(playerB_name)

        # Check if the player adding the game is one of the players
        if playerA.phone_number != phone_number and playerB.phone_number != phone_number:
            raise PlayerNotInGameException()

        # Update ratings but don't commit yet
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
            raise GameNotFoundException(game_id)
        else:
            game = self.session.query(Game).filter_by(id=game_id).first()
            playerA = self.session.query(Player).filter_by(id=game.playerA).first()
            playerB = self.session.query(Player).filter_by(id=game.playerB).first()

            if (not playerA or playerA.phone_number != phone_number) and (not playerB or playerB.phone_number != phone_number):
                raise PlayerNotInGameException()

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
            raise PlayerNotInRatingException(playerA.name, playerB.name)
        elif not playerA_rating:
            raise PlayerNotInRatingException(playerA.name)
        elif not playerB_rating:
            raise PlayerNotInRatingException(playerB.name)

        assert playerA_rating.rating
        assert playerB_rating.rating
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
            raise GameTypeNotSupportedException(game_type)

        # Update the ratings
        playerA_rating.rating += rating_change
        playerB_rating.rating -= rating_change

        # Update the games won and lost
        playerA_rating.games_won += scoreA
        playerA_rating.games_lost += scoreB

        playerB_rating.games_won += scoreB
        playerB_rating.games_lost += scoreA

        # Update the winning quote
        playerA_rating.winning_quote = playerA_rating.games_won / (playerA_rating.games_won + playerA_rating.games_lost)
        playerB_rating.winning_quote = playerB_rating.games_won / (playerB_rating.games_won + playerB_rating.games_lost)

        # Update the last_changed date
        playerA_rating.last_change = datetime.now()
        playerB_rating.last_change = datetime.now()

        self.logger.info(f"Rating für Spieler {playerA.name} und {playerB.name} aktualisiert.")

        return rating_change

    def rating_image(self):
        try:
            # Query
            query = self.session.query(
                func.row_number().over(order_by=Rating.rating.desc()).label("Platz"),
                Player.name.label("Namen"),
                Rating.rating.label("Rating"),
                Rating.winning_quote.label("Gewinnquote (%)"),
                Rating.games_won.label("Spiele (G)"),
                Rating.games_lost.label("Spiele (V)"),
                Rating.last_change.label("Letze Änderung"),
            ).join(Rating, Player.id == Rating.player)

            result = query.all()

            # Dataframe, styling and export
            data = pd.DataFrame(result)
            data_styled = (
                data.style.format({"Letze Änderung": "{:%d %b, %Y}", "Rating": "{:.2f}", "Gewinnquote (%)": "{:.2%}"})
                .set_caption("BV-Q-Club Rating Tabelle")
                .set_properties(**{"background-color": "#FFCFC9", "color": "black"}, subset=["Spiele (V)"])
                .set_properties(**{"background-color": "#C9FFC9", "color": "black"}, subset=["Spiele (G)"])
                .set_properties(**{"background-color": "#BEEAE5", "color": "black"}, subset=["Rating"])
                .set_properties(**{"background-color": "#FFB347", "color": "black"}, subset=["Gewinnquote (%)"])
                .hide(axis="index")
            )

            dfi.export(data_styled, "./rating.png", table_conversion="matplotlib")

            # Upload to storage
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
            self.logger.error(f"Fehler beim Erstellen des Ratings: {e}")
            return "Fehler beim Erstellen des Ratings. Bitte versuche es später erneut."
