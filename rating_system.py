import logging
import zipfile
from datetime import datetime
from os import environ, remove

import dataframe_image as dfi
import pandas as pd
from dotenv import load_dotenv
from fuzzywuzzy import fuzz, process
from sentry_sdk import capture_exception
from sqlalchemy import create_engine, func
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import sessionmaker
from supabase import Client, create_client

from utils.constants import BASIS_POINTS
from utils.exceptions import *
from utils.models import Base, Game, Player, Rating


class RatingSystem:
    def __init__(self):
        load_dotenv()
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
            force=True,
        )
        username = environ["SUPABASE_USER"]
        password = environ["SUPABASE_PASSWORD"]
        host = environ["SUPABASE_HOST"]
        port = environ["SUPABASE_PORT"]
        dbname = environ["SUPABASE_NAME"]
        self.engine = create_engine(f"postgresql+psycopg2://{username}:{password}@{host}:{port}/{dbname}")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

        url: str = environ["SUPABASE_URL"]
        key: str = environ["SUPABASE_KEY"]
        self.supabase: Client = create_client(url, key)

    def get_names(self):
        session = self.Session()
        try:
            names = session.query(Player.name).all()
            return [row[0] for row in names]
        except Exception as e:
            session.rollback()
            capture_exception(e)
            logging.error(f"Transaction failed: {e}")
        finally:
            session.close()

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
    ):
        session = self.Session()
        try:
            existing_player = session.query(Player).filter_by(phone_number=phone_number).first()
            if existing_player:
                logging.info(f"Spieler {existing_player.name} bereits in der Datenbank vorhanden.")
                raise PlayerAlreadyExistsException(existing_player.name)

            new_player = Player(name=name, phone_number=phone_number)

            session.add(new_player)
            session.commit()
            logging.info(f"Neuer Spieler {name} wurde zur Datenbank hinzugefügt.")
        except Exception as e:
            session.rollback()
            capture_exception(e)
            logging.error(f"Transaction failed: {e}")
            raise e
        finally:
            session.close()

    def delete_player(self, phone_number: str, name: str = None):
        session = self.Session()
        try:
            if phone_number == environ["ADMIN_PHONE_NUMBER"] and name:
                logging.info(f"Admin löscht Spieler {name}.")
                player = session.query(Player).filter_by(name=name).first()

                if not player:
                    raise PlayerNotFoundException(name)

                session.delete(player)
                session.commit()
                logging.info(f"Spielereintrag für {player.name} aus der Datenbank gelöscht.")

            else:
                logging.info(f"Suche {phone_number} in der Datenbank.")
                player = session.query(Player).filter_by(phone_number=phone_number).first()
                if not player:
                    raise PlayerNotFoundException(f"mit Handynummer: {phone_number}")
                logging.info(f"Spieler {player.name} in der Datenbank gefunden.")

                name = player.name

                session.delete(player)
                session.commit()
                logging.info(f"Spielereintrag für {player.name} aus der Datenbank gelöscht.")
                return name
        except Exception as e:
            session.rollback()
            capture_exception(e)
            logging.error(f"Transaction failed: {e}")
            raise e
        finally:
            session.close()

    def add_player_to_rating(self, phone_number: str):
        session = self.Session()
        try:
            player = session.query(Player).filter_by(phone_number=phone_number).first()

            if not player:
                raise PlayerNotFoundException(f"mit Handynummer: {phone_number}")

            existing_rating = session.query(Rating).filter_by(player=player.id).first()

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

            session.add(new_rating)
            session.commit()
            logging.info(f"Spieler {player.name} zum Rating hinzugefügt.")
        except Exception as e:
            session.rollback()
            capture_exception(e)
            logging.error(f"Transaction failed: {e}")
            raise e
        finally:
            session.close()

    def delete_player_from_rating(self, phone_number: str):
        session = self.Session()
        try:
            player = session.query(Player).filter_by(phone_number=phone_number).first()

            if not player:
                raise PlayerNotFoundException(f"mit Handynummer: {phone_number}")

            existing_rating = session.query(Rating).filter_by(player=player.id).first()

            if not existing_rating:
                logging.info(f"Spieler {player.name} nicht im Rating.")
                raise PlayerNotInRatingException(player.name)

            session.query(Rating).filter_by(player=player.id).delete()
            session.commit()
            logging.info(f"Spieler {player.name} aus dem Rating gelöscht.")
        except Exception as e:
            session.rollback()
            capture_exception(e)
            logging.error(f"Transaction failed: {e}")
            raise e
        finally:
            session.close()

    def add_games(self, playerA, playerB, scores, game_type, phone_number) -> list[tuple[str, float]]:
        changes = []
        for score1, score2 in scores:
            id, rating_change = self.add_game(playerA, playerB, score1, score2, game_type, phone_number)
            changes.append((id, rating_change))
        return changes

    def add_game(self, playerA_name, playerB_name, scoreA, scoreB, game_type, phone_number) -> tuple[str, float]:
        session = self.Session()
        try:
            playerA_name = self.find_closest_name(playerA_name)
            playerB_name = self.find_closest_name(playerB_name)

            playerA = session.query(Player).filter_by(name=playerA_name).first()
            playerB = session.query(Player).filter_by(name=playerB_name).first()

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
                not session.query(Rating).filter_by(player=playerA.id).first()
                or not session.query(Rating).filter_by(player=playerB.id).first()
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
                session=session,
            )
            session.add(new_game)
            session.commit()
            logging.info(
                f"Neues Spiel hinzugefügt (ID: {new_game.id}) zwischen {playerA_name} und {playerB_name}\nRating change {new_game.rating_change}."
            )

            return (str(new_game.id), new_game.rating_change)
        except Exception as e:
            session.rollback()
            capture_exception(e)
            logging.error(f"Transaction failed: {e}")
            raise e
        finally:
            session.close()

    def delete_game(self, game_id: str, phone_number: str):
        session = self.Session()
        try:
            if not session.query(Game).filter_by(id=game_id).first():
                raise GameNotFoundException(game_id)

            game = session.query(Game).filter_by(id=game_id).first()
            playerA = session.query(Player).filter_by(id=game.playerA).first()
            playerB = session.query(Player).filter_by(id=game.playerB).first()

            # Check if game is too old over 1 hours
            if (datetime.now() - game.created_at).minutes > 60:
                raise GameTooOldException(game_id)

            if phone_number == environ["ADMIN_PHONE_NUMBER"]:
                logging.info(f"Admin {phone_number} löscht Spiel.")
            else:
                if (not playerA or playerA.phone_number != phone_number) and (
                    not playerB or playerB.phone_number != phone_number
                ):
                    raise PlayerNotInGameException()

            ratingA = session.query(Rating).filter_by(player=game.playerA).first()
            ratingB = session.query(Rating).filter_by(player=game.playerB).first()

            if not ratingA or not ratingB:
                raise PlayerNotInRatingException(playerA.name, playerB.name)

            ratingA.games_won -= game.scoreA
            ratingA.games_lost -= game.scoreB

            ratingB.games_won -= game.scoreB
            ratingB.games_lost -= game.scoreA

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

            session.query(Game).filter_by(id=game_id).delete()
            # Ratings should be updated in the after_delete_game event
            session.commit()
            logging.info(f"Spiel mit ID {game_id} gelöscht.")
        except Exception as e:
            session.rollback()
            capture_exception(e)
            logging.error(f"Transaction failed: {e}")
            raise e
        finally:
            session.close()

    def rating_image(self):
        """Creates a table with the current ratings and exports it as an image.
        See URLS:
            https://medium.com/@romina.elena.mendez/transform-your-pandas-dataframes-styles-colors-and-emojis-bf938d6e98a2
            https://towardsdatascience.com/make-your-tables-look-glorious-2a5ddbfcc0e5
        """
        session = self.Session()
        try:
            query = session.query(
                func.row_number().over(order_by=Rating.rating.desc()).label("Platz"),
                Player.name.label("Name"),
                Rating.rating.label("Rating"),
                Rating.winning_quote.label("Gewinnquote (%)"),
                Rating.games_won.label("Spiele (G)"),
                Rating.games_lost.label("Spiele (V)"),
                Rating.last_change.label("Letze Änderung"),
            )

            result = query.join(Player, Player.id == Rating.player).all()

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
            try:
                storage.create_bucket("rating", options={"public": True})
                logging.info("Ein neuer Bucket für das Rating-Tabellenbild wurde erstellt.")
            except:
                logging.info("Bucket für das Rating-Tabellenbild bereits vorhanden.")

            ratingBucket = storage.from_("rating")

            with open("./rating.png", "rb") as f:
                storage.empty_bucket("rating")
                ratingBucket.upload(path="./rating.png", file=f, file_options={"content-type": "image/png"})

                res = ratingBucket.get_public_url("rating.png")
                logging.info("Das Rating-Tabellenbild wurde exportiert.")
                return res
        except Exception as e:
            session.rollback()
            capture_exception(e)
            logging.error(f"Transaction failed: {e}")
            raise e
        finally:
            session.close()

    def export_database(self):
        session = self.Session()
        try:
            # Upload to storage
            storage = self.supabase.storage
            try:
                storage.create_bucket("backup")
            except:
                logging.info("Bucket für das Backup bereits vorhanden.")

            backup_bucket = storage.from_("backup")

            # Delete backups older than 7 days
            files = backup_bucket.list()
            timestamp_format = "%Y-%m-%d %H:%M:%S"
            logging.info(files)

            for file in files:
                file_name = file["name"]
                if file_name == ".emptyFolderPlaceholder":
                    continue
                timestamp = file_name.split("_")[1].split(".")[0]
                timestamp = datetime.strptime(timestamp, timestamp_format)
                if (datetime.now() - timestamp).days > 7:
                    backup_bucket.remove(file["name"])
                    logging.info(f"Backup {file['name']} wurde gelöscht.")

            # Fetch all ratings and games
            ratings = session.query(Rating).all()
            games = session.query(Game).all()

            # Create csv from ratings and games
            rating_df = pd.DataFrame(
                [
                    {
                        "player": rating.player,
                        "rating": rating.rating,
                        "games_won": rating.games_won,
                        "games_lost": rating.games_lost,
                    }
                    for rating in ratings
                ]
            )
            game_df = pd.DataFrame(
                [
                    {
                        "playerA": game.playerA,
                        "playerB": game.playerB,
                        "scoreA": game.scoreA,
                        "scoreB": game.scoreB,
                        "race_to": game.race_to,
                        "disciplin": game.disciplin,
                        "rating_change": game.rating_change,
                    }
                    for game in games
                ]
            )

            # Export to csv
            rating_df.to_csv("ratings.csv", index=False)
            game_df.to_csv("games.csv", index=False)

            # Create zip from csvs
            with zipfile.ZipFile("backup.zip", "w") as zf:
                zf.write("ratings.csv")
                zf.write("games.csv")

            # Upload to storage with timestamp
            timestamp = datetime.now().strftime(timestamp_format)

            with open("backup.zip", "rb") as f:
                backup_bucket.upload(path=f"backup_{timestamp}.zip", file=f, file_options={"content-type": "application/zip"})
                logging.info("Die Datenbank wurde exportiert.")

                # Delete local files
                remove("ratings.csv")
                remove("games.csv")
                remove("backup.zip")
        except Exception as e:
            session.rollback()
            capture_exception(e)
            logging.error(f"Transaction failed: {e}")
            raise e
        finally:
            session.close()

    def adjust_rating(self, name, rating, games_won, games_lost, phone_number=None):
        session = self.Session()
        try:
            if phone_number and phone_number != environ["ADMIN_PHONE_NUMBER"]:
                raise AdminPermissionException()

            name = self.find_closest_name(name)
            player = session.query(Player).filter_by(name=name).first()
            if not player:
                raise PlayerNotFoundException(name)

            player_rating = session.query(Rating).filter_by(player=player.id).first()
            if not player_rating:
                raise PlayerNotInRatingException(name)

            player_rating.rating = rating
            player_rating.games_won = games_won
            player_rating.games_lost = games_lost
            if games_won + games_lost != 0:
                player_rating.winning_quote = games_won / (games_won + games_lost)
            player_rating.last_change = datetime.now()

            session.commit()
            logging.info(f"Rating von {name} wurde angepasst auf {rating}.")
        except Exception as e:
            session.rollback()
            capture_exception(e)
            logging.error(f"Transaction failed: {e}")
            raise e
        finally:
            session.close()

    def apply_rating_decay(self):
        session = self.Session()
        try:
            ratings = session.query(Rating).all()

            # Check if rating is older than 30 days
            for rating in ratings:
                if (datetime.now() - rating.last_change).days > 30:
                    rating.rating = rating.rating * 0.97
                    rating.last_change = datetime.now()
                    logging.info(f"Rating von {rating.player} wurde um 3% reduziert.")

            session.commit()
            logging.info("Rating Decay wurde angewendet.")
        except Exception as e:
            session.rollback()
            capture_exception(e)
            logging.error(f"Transaction failed: {e}")
            raise e
        finally:
            session.close()
