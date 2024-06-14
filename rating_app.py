import logging
from flask import Flask, request, session, jsonify
import re
import json
import requests
from waitress import serve
from exceptions import RatingException
from os import urandom, environ
from enum import Enum
from ratingSystem import RatingSystem
from string import Template
from message_provider import MessageProvider


class UserState(Enum):
    INITIAL = "initial"

    # Player states
    PLAYER = "player"
    ADD_PLAYER = "add_player"

    # Game states
    GAME = "game"
    ADD_GAME = "add_game"
    DELETE_GAME = "delete_game"


logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
    force=True,
)


app = Flask(__name__)

app.secret_key = urandom(24)

headers_template = Template('{"Authorization": "Bearer ${token}", "Content-Type": "application/json"}')
headers = json.loads(headers_template.substitute(token=environ["WHATSAPP_TOKEN"]))

URL = "https://graph.facebook.com/v19.0/325890010616383/messages"


@app.route("/")
def test():
    return "<pre>Nothing to see here. Checkout README.md to start.</pre>"


@app.get("/whatsapp")
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    # Check if a token and mode are in the query string
    if mode and token:
        # Check the mode and token sent are correct
        if mode == "subscribe" and token == environ["WHATSAPP_WEBHOOK_TOKEN"]:
            # Respond with the challenge token from the request
            return challenge, 200
        else:
            # Respond with '403 Forbidden' if verify tokens do not match
            return "Forbidden", 403


@app.route("/whatsapp", methods=["POST"])
def whatsapp_message():
    data = request.get_json()
    logger.info(f"Received data: {data}")
    logger.info(f"Received phone_no_id: {data.get('phone_number_id')}")

    phone_number_id = data["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"]
    phone_number = data["entry"][0]["changes"][0]["value"]["messages"][0]["from"]
    incoming_message = data["entry"][0]["changes"][0]["value"]["messages"][0]["text"]["body"]

    print(f"Phone Number ID: {phone_number_id}")
    print(f"From: {phone_number}")
    print(f"Body: {incoming_message}")

    if phone_number_id and phone_number and message:
        if phone_number not in session:
            session[phone_number] = {"messages": [], "state": UserState.INITIAL.value}

        session[phone_number]["messages"].append(incoming_message)
        logger.debug(f"Session data: {session.get(phone_number, None)}")

        if session[phone_number]["state"] == UserState.INITIAL.value:
            message_provider = MessageProvider()
            url, headers, payload = message_provider.send_interactive_message(phone_number_id, phone_number)
            response = requests.post(url, json=payload, headers=headers)
            return jsonify(response.json()), response.status_code
        else:
            message_processor = MessageProcessor()
            message = message_processor.handle_message(incoming_message, phone_number, session[phone_number]["state"])

            logger.debug(f"Session data: {session.get(phone_number, None)}")

            url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"
            payload = {
                "messaging_product": "whatsapp",
                "to": phone_number,
                "text": {"body": message},
            }

            response = requests.post(url, json=payload, headers=headers)
            return jsonify(response.json()), response.status_code
    return jsonify({"error": "An error occurred"}), 500


class MessageProcessor:
    def __init__(self):
        self.ratingSystem = RatingSystem()

    def handle_message(self, message: str, phone_number: str, current_state: str) -> str:
        if current_state == UserState.INITIAL.value:
            return self.handle_initial_state(message, phone_number)

        elif current_state == UserState.PLAYER.value:
            return self.handle_player(message, phone_number)
        elif current_state == UserState.ADD_PLAYER.value:
            return self.handle_add_player(message, phone_number)

        elif current_state == UserState.GAME.value:
            return self.handle_game(message, phone_number)
        elif current_state == UserState.ADD_GAME.value:
            return self.handle_add_game(message, phone_number)
        elif current_state == UserState.DELETE_GAME.value:
            return self.handle_delete_game(message, phone_number)

        else:
            session.pop(phone_number, None)
            return "Eingabe nicht erkannt."

    def handle_initial_state(self, message, phone_number) -> str:
        if message.lower() == "rating":
            session.pop(phone_number, None)
            return self.ratingSystem.rating_image()
        elif message.lower().startswith("spieler"):
            session[phone_number]["state"] = UserState.PLAYER.value
            return "Bitte geben Sie ein was Sie machen möchten:\nHinzufügen, Löschen, Rating hinzufügen"
        elif message.lower().startswith("spiel"):
            session[phone_number]["state"] = UserState.GAME.value
            return "Bitte geben Sie ein was Sie machen möchten:\nNeu, Löschen"
        else:
            session.pop(phone_number, None)
            return "Eingabe nicht erkannt."

    def handle_rating(self):
        return self.ratingSystem.rating_image()

    def handle_player(self, message, phone_number):
        if message.lower().startswith("hinzufügen"):
            session[phone_number]["state"] = UserState.ADD_PLAYER.value
            return "Bitte gib deinen Namen ein."
        elif message.lower().startswith("löschen"):
            session.pop(phone_number, None)
            try:
                name = self.ratingSystem.delete_player(phone_number)
                return f"Spieler {name} erfolgreich gelöscht."
            except RatingException as e:
                return f"Fehler: {e}"

        elif message.lower().startswith("rating hinzufügen"):
            try:
                self.ratingSystem.add_player_to_rating(phone_number)
                return f"Du wurdest zum Rating hinzugefügt."
            except RatingException as e:
                return f"Fehler: {e}"
        else:
            session.pop(phone_number, None)
            return "Eingabe nicht erkannt."

    def handle_add_player(self, name, phone_number):
        try:
            self.ratingSystem.add_player(name, phone_number)
            return f"Spieler {name} wurde hinzugefügt."
        except RatingException as e:
            return f"Fehler: {e}"

    def handle_add_rating(self, phone_number):
        try:
            self.ratingSystem.add_player_to_rating(phone_number)
            return f"Rating wurde hinzugefügt."
        except RatingException as e:
            return f"Fehler: {e}"

    def handle_game(self, message, phone_number):
        if message.lower().startswith("neu"):
            session[phone_number]["state"] = UserState.ADD_GAME.value
            return "Bitte geben Sie ein was Sie machen möchten:\nSpieltyp\nSpieler A:Spieler B\nScoreA:ScoreB\n..."
        elif message.lower().startswith("löschen"):
            session[phone_number]["state"] = UserState.DELETE_GAME.value
            return "Bitte geben Sie die ID des Spiels ein, das Sie löschen möchten."
        else:
            session.pop(phone_number, None)
            return "Eingabe nicht erkannt."

    def handle_add_game(self, message, phone_number):
        try:
            game_type = message.split("\n")[0]
            names = message.split("\n")[1]
            nameA, nameB = names.strip().split(":")
            scores = [tuple(map(int, match)) for match in re.findall(r"\b(\d+):(\d+)\b", message)]

            logger.info(f"Identified matches: {game_type}, {names}, {scores}")

            ids = self.ratingSystem.add_games(nameA, nameB, scores, game_type, phone_number)

            return "Spiele hinzugefügt. IDs: " + ", ".join(map(str, ids))
        except RatingException as e:
            return f"Fehler: {e}"
        except Exception as e:
            return f"Fehler: {e}"

    def handle_delete_game(self, message, phone_number):
        try:
            id = int(message)
            self.ratingSystem.delete_game(id, phone_number)
            return "Spiel wurde gelöscht."
        except RatingException as e:
            return f"Fehler: {e}"
        except Exception as e:
            return f"Fehler: {e}"


if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=8080)
