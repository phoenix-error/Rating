from enums import Liga, GameType
from exceptions import *
from datetime import datetime
from math import floor
import pandas as pd
import dataframe_image as dfi
from sqlalchemy import create_engine, func, event
from sqlalchemy.orm import sessionmaker
from models import Base, Player, Rating, Game
from constants import (
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
from fuzzywuzzy import fuzz, process


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

        url: str = environ["SUPABASE_URL"]
        key: str = environ["SUPABASE_KEY"]
        self.supabase: Client = create_client(url, key)

    def get_names(self):
        names = self.session.query(Player.name).all()
        return [row[0] for row in names]

    def find_closest_name(self, name) -> str:
        logging.info(f"Suche nach Namen {name} in der Datenbank.")

        matches = process.extractOne(name, self.get_names(), score_cutoff=75, scorer=fuzz.token_sort_ratio)
        if matches:
            logging.info(matches)
            return matches[0]
        else:
            logging.info(f"Name {name} konnte nicht in der Datenbank gefunden werden.")
            raise PlayerNotFoundException(name)

    def add_player(
        self,
        name: str,
        phone_number: str,
    ) -> str:
        existing_player = self.session.query(Player).filter_by(phone_number=phone_number).first()
        if existing_player:
            logging.info(f"Spieler {existing_player.name} bereits in der Datenbank vorhanden.")
            raise PlayerAlreadyExistsException(existing_player.name)

        new_player = Player(name=name, phone_number=phone_number)

        self.session.add(new_player)
        self.session.commit()
        logging.info(f"Neuer Spieler {name} wurde zur Datenbank hinzugefügt.")

    def delete_player(self, phone_number: str, name: str = None):
        if phone_number == environ["ADMIN_PHONE_NUMBER"] and name:
            logging.info(f"Admin löscht Spieler {name}.")
            player = self.session.query(Player).filter_by(name=name).first()

            if not player:
                raise PlayerNotFoundException(name)

            self.session.delete(player)
            self.session.commit()
            logging.info(f"Spielereintrag für {player.name} aus der Datenbank gelöscht.")
            return

        try:
            logging.info(f"Suche {phone_number} in der Datenbank.")
            player = self.session.query(Player).filter_by(phone_number=phone_number).one()
            logging.info(f"Spieler {player.name} in der Datenbank gefunden.")

            name = player.name

            self.session.delete(player)
            self.session.commit()
            logging.info(f"Spielereintrag für {player.name} aus der Datenbank gelöscht.")
            return name
        except NoResultFound:
            raise PlayerNotFoundException(f"mit Handynummer: {phone_number}")

    def add_player_to_rating(self, phone_number: str):
        player = self.session.query(Player).filter_by(phone_number=phone_number).first()

        if not player:
            raise PlayerNotFoundException(f"mit Handynummer: {phone_number}")

        existing_rating = self.session.query(Rating).filter_by(player=player.id).first()

        if existing_rating:
            logging.info(f"Spieler {player.name} bereits im Rating.")
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
        logging.info(f"Spieler {player.name} zum Rating hinzugefügt.")

    def delete_player_from_rating(self, phone_number: str):
        player = self.session.query(Player).filter_by(phone_number=phone_number).first()

        if not player:
            raise PlayerNotFoundException(f"mit Handynummer: {phone_number}")

        existing_rating = self.session.query(Rating).filter_by(player=player.id).first()

        if not existing_rating:
            logging.info(f"Spieler {player.name} nicht im Rating.")
            raise PlayerNotInRatingException(player.name)

        self.session.query(Rating).filter_by(player=player.id).delete()
        self.session.commit()
        logging.info(f"Spieler {player.name} aus dem Rating gelöscht.")

    def add_games(self, playerA, playerB, scores, game_type, phone_number) -> list[tuple[str, float]]:
        changes = []
        for score1, score2 in scores:
            id, rating_change = self.add_game(playerA, playerB, score1, score2, game_type, phone_number)
            changes.append((id, rating_change))
        return changes

    def add_game(self, playerA_name, playerB_name, scoreA, scoreB, game_type, phone_number) -> tuple[str, float]:
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

        if phone_number == environ["ADMIN_PHONE_NUMBER"]:
            logging.info(f"Admin {phone_number} fügt Spiel hinzu.")
        else:
            # Check if the player adding the game is one of the players
            if playerA.phone_number != phone_number and playerB.phone_number != phone_number:
                raise PlayerNotInGameException()

        # Check if ratings exist
        if (
            not self.session.query(Rating).filter_by(player=playerA.id).first()
            or not self.session.query(Rating).filter_by(player=playerB.id).first()
        ):
            raise PlayerNotInRatingException(playerA_name, playerB_name)

        # Rating should be updated in the the init of Game

        new_game = Game(
            playerA=playerA.id,
            playerB=playerB.id,
            scoreA=scoreA,
            scoreB=scoreB,
            race_to=max(scoreA, scoreB),
            disciplin=game_type,
            session=self.session,
        )
        self.session.add(new_game)
        self.session.commit()
        logging.info(
            f"Neues Spiel hinzugefügt (ID: {new_game.id}) zwischen {playerA_name} und {playerB_name}\nRating change {new_game.rating_change}."
        )

        return (str(new_game.id), new_game.rating_change)

    def delete_game(self, game_id: str, phone_number: str):
        if not self.session.query(Game).filter_by(id=game_id).first():
            raise GameNotFoundException(game_id)

        game = self.session.query(Game).filter_by(id=game_id).first()
        playerA = self.session.query(Player).filter_by(id=game.playerA).first()
        playerB = self.session.query(Player).filter_by(id=game.playerB).first()

        if phone_number == environ["ADMIN_PHONE_NUMBER"]:
            logging.info(f"Admin {phone_number} löscht Spiel.")
        else:
            if (not playerA or playerA.phone_number != phone_number) and (not playerB or playerB.phone_number != phone_number):
                raise PlayerNotInGameException()

        ratingA = self.session.query(Rating).filter_by(player=game.playerA).first()
        ratingB = self.session.query(Rating).filter_by(player=game.playerB).first()

        if not ratingA or not ratingB:
            raise PlayerNotInRatingException(playerA.name, playerB.name)

        ratingA.games_won -= game.scoreA
        ratingB.games_lost -= game.scoreB
        ratingA.rating -= game.rating_change
        ratingB.rating += game.rating_change

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

        self.session.query(Game).filter_by(id=game_id).delete()
        # Ratings should be updated in the after_delete_game event
        self.session.commit()
        logging.info(f"Spiel mit ID {game_id} gelöscht.")

    def rating_image(self):
        """Creates a table with the current ratings and exports it as an image.
        See URLS:
            https://medium.com/@romina.elena.mendez/transform-your-pandas-dataframes-styles-colors-and-emojis-bf938d6e98a2
            https://towardsdatascience.com/make-your-tables-look-glorious-2a5ddbfcc0e5
        """

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
            .set_properties(**{"text-align": "center"})
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
            logging.info("Ein neuer Bucket für das Rating-Tabellenbild wurde erstellt.")

        ratingBucket = storage.from_("rating")

        with open("./rating.png", "rb") as f:
            storage.empty_bucket("rating")
            ratingBucket.upload(path="./rating.png", file=f, file_options={"content-type": "image/png"})

            res = ratingBucket.get_public_url("rating.png")
            logging.info("Das Rating-Tabellenbild wurde exportiert.")
            return res

    def adjust_rating(self, name, rating, games_won, games_lost, phone_number=None):
        if phone_number and phone_number != environ["ADMIN_PHONE_NUMBER"]:
            raise AdminPermissionException()

        name = self.find_closest_name(name)
        player = self.session.query(Player).filter_by(name=name).first()
        if not player:
            raise PlayerNotFoundException(name)

        player_rating = self.session.query(Rating).filter_by(player=player.id).first()
        if not player_rating:
            raise PlayerNotInRatingException(name)

        player_rating.rating = rating
        player_rating.games_won = games_won
        player_rating.games_lost = games_lost
        if games_won + games_lost != 0:
            player_rating.winning_quote = games_won / (games_won + games_lost)
        player_rating.last_change = datetime.now()

        self.session.commit()
        logging.info(f"Rating von {name} wurde angepasst auf {rating}.")
