import logging
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from enums import GameType
from ratingSystem import RatingSystem
import re
from constants import GAMES_FILE
from typ import json
from typing import List
from models import JSONGame
import os
from enums import Liga
from exceptions import RatingException


if not os.path.exists("logs"):
    os.makedirs("logs")

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    filename="logs/app.log",
    filemode="a",
    format="%(asctime)s %(levelname)s %(message)s",
    force=True,
)

app = Flask(__name__)


@app.route("/")
def hello():
    return "Hello, World!"


@app.route("/whatsapp", methods=["POST"])
def whatsapp_message():
    incoming_msg = request.values.get("Body", "").strip()
    phone_number = request.values.get("From", "").strip()

    response = process_message(incoming_msg, phone_number)
    return str(response)


def process_message(message, phone_number):
    ratingSystem = RatingSystem()

    # Analyze message
    # If message is of form Löschen <id> then delete game with id <id>
    if message.lower().startswith(
        "löschen",
    ):
        matcher = re.match(r"löschen\s+(\d+)", message)
        if matcher is not None:
            ratingSystem.delete_game(int(matcher.group(1)))
        else:
            response = MessagingResponse()
            response.message("Fehler: Bitte gib eine gültige ID an.")
            return response

    if message.lower().startswith("spieler hinzufügen"):
        pattern = r"spieler hinzufügen\s*?(\w+, \w+)\s*([a-zA-Z]+)\s*([a-zA-Z]+)?"
        match = re.search(pattern, message, re.IGNORECASE)
        if match and match.group(1) and match.group(2):
            name = match.group(1)
            country = match.group(2)
            liga = match.group(3)
        else:
            return create_response(
                f"Spieler konnte nicht hinzugefügt werden.\nFormat: Spieler hinzufügen <name> <country> <liga>"
            )

        try:
            if not liga:
                ratingSystem.add_player(name, phone_number, country)
            else:
                ratingSystem.add_player(name, phone_number, country, liga)
            return create_response(f"Spieler {name} wurde hinzugefügt.")
        except RatingException as e:
            return create_response(f"Fehler: {e}")

    # If message is of form Spieler löschen <name> then delete player
    if message.startswith("spieler löschen"):
        pattern = r"spieler löschen\s*?(\w+, \w+)"
        match = re.search(pattern, message, re.IGNORECASE)
        name = match.group(0)

        if match and match.group(1):
            try:
                ratingSystem.delete_player(match.group(1))
            except RatingException as e:
                return create_response(f"Fehler: {e}")
        else:
            return create_response(
                f"Spieler konnte nicht gelöscht werden.\nFormat: Spieler löschen <name>"
            )

    # If message is of form Rating hinzufügen <name> then add player to rating
    if message.startswith("rating hinzufügen"):
        pattern = r"rating hinzufügen\s*?(\w+, \w+)"
        match = re.search(pattern, message, re.IGNORECASE)

        if match and match.group(1):
            name = match.group(1)
            try:
                ratingSystem.add_player_to_rating(name)
            except RatingException as e:
                return create_response(f"Fehler: {e}")
        else:
            return create_response(
                f"Spieler konnte nicht hinzugefügt werden.\nFormat: Rating hinzufügen <name>"
            )

    # If message is of form Rating then return rating table
    pattern = r"\s*rating/s*"
    if re.match(pattern, message, re.IGNORECASE):
        ratingSystem.rating_image()
        response = MessagingResponse()
        message = response.message("Rating Tabelle")
        message.media("https://rating-svbi.onrender.com/RatingImage.png")
        return response

    # Check if message starts with a GameType
    # get first line
    gameType = message.splitlines()[0]
    if gameType in [gameType.value for gameType in GameType]:
        # If message is of form Spiel <name1>: <name2> <score1>:<score2> then add game
        try:
            playerA, playerB, scores, game_type = extract_information(message)
            with open(GAMES_FILE, "r+") as file:
                games: List[JSONGame] = json.load(file, List[JSONGame])
                for scoreA, scoreB in scores:
                    race_to = max(scoreA, scoreB)
                    game = JSONGame(
                        playerA, playerB, scoreA, scoreB, race_to, game_type
                    )
                    games.append(game)
                file.seek(0)
                json.dump(file, games)

            score_string = "\n".join(
                [f"{scoreA}:{scoreB}" for (scoreA, scoreB) in scores]
            )
            message = f"""
        Spiel wurde hinzugefügt:
            {playerA} vs. {playerB}

        *{"Ergebnisse" if len(scores) > 1 else "Ergebnis"}:* 
            {score_string}
            """
            return create_response(message)
        except Exception as e:
            logger.error(f"NameError: {e}")
            response = MessagingResponse()
            response.message(f"Error: {e}")
            return response

    return create_response(
        "Fehler: Eingabe konnte nicht zugeordnet werden. Für mehr Informationen bitte in die Beschreibung schauen."
    )


def create_response(message):
    response = MessagingResponse()
    response.message(message)
    return response


def extract_information(message):
    message_parts = message.splitlines()
    gameType = message_parts[0].strip()
    names = message_parts[1]
    scores = message_parts[2:]

    names_pattern = r"^\s*([a-zA-Z]+)\s*:\s*([a-zA-Z]+)\s*"
    names_match = re.search(names_pattern, names)

    if gameType not in [gameType.value for gameType in GameType]:
        raise NameError(
            "Spieltyp konnte nicht erkannt werden. Bitte überprüfe die Eingabe.\nFormat: Spiel\nName1: Name2\nScore1: Score2\n...\nEs sind nur 'Normal' und '14.1' erlaubt."
        )

    if names_match:
        name1 = names_match.group(1)
        name2 = names_match.group(2)

        ratingSystem = RatingSystem()
        name1_matched = ratingSystem.find_closest_name(name1)
        name2_matched = ratingSystem.find_closest_name(name2)
    else:
        raise NameError(
            "Namen konnten nicht erkannt werden. Bitte überprüfe die Eingabe.\nFormat: Spiel\nName1: Name2\nScore1: Score2\n..."
        )

    scores = clean_scores(scores)

    return name1_matched, name2_matched, scores, gameType


def clean_scores(scores):
    result = []
    score_pattern = r"^\s*(\d+)\s*:\s*(\d+)\s*"
    for score in scores:
        score_match = re.search(score_pattern, score)
        if score_match:
            result.append((int(score_match.group(1)), int(score_match.group(2))))
        else:
            logger.critical(f"Erebnis konnte nicht geparst werden: {score}")
    return result


if __name__ == "__main__":
    app.run(debug=True, port=8080, host="0.0.0.0")
