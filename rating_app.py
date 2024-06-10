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
    message = message.lower()

    # Analyze message
    # If message is of form Löschen <id> then delete game with id <id>
    if message.startswith("löschen"):
        try:
            game_id = int(message.split()[1])
            ratingSystem.delete_game(game_id)
        except Exception as e:
            logger.error(f"Error: {e}")
            response = MessagingResponse()
            response.message(f"Error: {e}")
            return response

    # If message is of form Spieler hinzufügen\n<name> <country> (optional) then add player
    if message.startswith("spieler hinzufügen"):
        try:
            message_parts = message.replace("spieler hinzufügen", "").splitlines()
            name = message_parts[0].strip()
            country = message_parts[1] if len(message_parts) >= 2 else "deutschland"
            liga = message_parts[2] if len(message_parts) >= 3 else Liga.KEINE
            # Check if liga is valid
            if liga not in [liga.value for liga in Liga]:
                response = MessagingResponse()
                response.message(
                    f"Liga konnte nicht erkannt werden. Bitte überprüfe die Eingabe.\nFormat: Spieler hinzufügen <name> <country> <liga>"
                )
                return response

            ratingSystem.add_player(name, phone_number, country, liga)
            response = MessagingResponse()
            response.message(f"Spieler {name} wurde hinzugefügt.")
            return response
        except Exception as e:
            logger.error(f"Error: {e}")
            response = MessagingResponse()
            response.message(f"Error: {e}")
            return response

    # If message is of form Spieler löschen <name> then delete player
    if message.startswith("spieler löschen"):
        try:
            name = message.split()[2]
            ratingSystem.delete_player(name)
            response = MessagingResponse()
            response.message(f"Spieler {name} wurde gelöscht.")
            return response
        except Exception as e:
            logger.error(f"Error: {e}")
            response = MessagingResponse()
            response.message(f"Error: {e}")
            return response

    # If message is of form Rating hinzufügen <name> then add player to rating
    if message.startswith("rating hinzufügen"):
        try:
            name = message.split()[2]
            ratingSystem.add_player_to_rating(name)
            response = MessagingResponse()
            response.message(f"Spieler {name} wurde zur Ratingliste hinzugefügt.")
            return response
        except Exception as e:
            logger.error(f"Error: {e}")
            response = MessagingResponse()
            response.message(f"Error: {e}")
            return response

    # If message is of form Rating then return rating table
    if message == "rating":
        ratingSystem.rating_image()
        response = MessagingResponse()
        message = response.message("Rating Tabelle")
        message.media("https://rating-svbi.onrender.com/RatingImage.png")
        return response

    # If message is of form Spiel <name1>: <name2> <score1>:<score2> then add game
    try:
        playerA, playerB, scores, game_type = extract_information(message)
        with open(GAMES_FILE, "r+") as file:
            games: List[JSONGame] = json.load(file, List[JSONGame])
            for scoreA, scoreB in scores:
                race_to = max(scoreA, scoreB)
                game = JSONGame(playerA, playerB, scoreA, scoreB, race_to, game_type)
                games.append(game)
            file.seek(0)
            json.dump(file, games)

        return response_builder(playerA, playerB, scores)
    except Exception as e:
        logger.error(f"NameError: {e}")
        response = MessagingResponse()
        response.message(f"Error: {e}")
        return response


def response_builder(playerA, playerB, scores):
    response = MessagingResponse()

    score_string = "\n".join([f"{scoreA}:{scoreB}" for (scoreA, scoreB) in scores])
    message = f"""
Spiel wurde hinzugefügt:
    {playerA} vs. {playerB}

*{"Ergebnisse" if len(scores) > 1 else "Ergebnis"}:* 
    {score_string}
    """
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
