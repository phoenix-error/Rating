import logging
from flask import Flask, request, jsonify
import re
import requests
from waitress import serve
from exceptions import RatingException
from os import urandom, environ
from enum import Enum
from ratingSystem import RatingSystem
from message_provider import MessageProvider
from dotenv import load_dotenv

load_dotenv()


class UserState(Enum):
    INITIAL = "initial"

    ADD_PLAYER = "add_player"

    ADD_GAME = "add_game"
    DELETE_GAME = "delete_game"


logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
    force=True,
)


app = Flask(__name__)

session = dict()


url_for = lambda phone_number_id: f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"
headers = {
    "Authorization": "Bearer " + environ["WHATSAPP_TOKEN"],
    "Content-Type": "application/json",
}


@app.route("/")
def test():
    return "<pre>Nothing to see here. Checkout README.md to start.</pre>"


@app.get("/whatsapp")
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    logger.info(f"Received request with mode: {mode}, token: {token}, challenge: {challenge}")

    # Check if a token and mode are in the query string
    if mode and token:
        # Check the mode and token sent are correct
        if mode == "subscribe" and token == environ["WHATSAPP_WEBHOOK_TOKEN"]:
            # Respond with the challenge token from the request
            return challenge, 200
        else:
            # Respond with '403 Forbidden' if verify tokens do not match
            return jsonify({"status": "error", "message": "Verification failed"}), 403
    return jsonify({"status": "error", "message": "Missing parameters"}), 400


@app.route("/whatsapp", methods=["POST"])
def whatsapp_message():
    data = request.get_json()

    if data.get("object") == "whatsapp_business_account":
        entry = data.get("entry")
        if entry and entry[0].get("changes"):
            change = entry[0].get("changes")[0]
            if change and change.get("value"):
                value = change.get("value")
                if value.get("metadata") and value.get("messages"):
                    if value["metadata"]["phone_number_id"] and value["messages"][0]:
                        phone_number_id = value["metadata"]["phone_number_id"]
                        message = value["messages"][0]
                        try:
                            handle_message(phone_number_id, message)
                        except Exception as e:
                            logger.exception(f"Error while handling message. {e}")
                            return "Error", 200

    return "OK", 200


def handle_message(phone_number_id, message):
    logger.info(f"Received message: {message} with phone number id: {phone_number_id}")

    phone_number = message["from"]
    logger.info(f"Inital Session: {session.get(phone_number)}")

    match message["type"]:
        case "text":
            incoming_message = message["text"]["body"]
        case "interactive":
            if message["interactive"]["type"] == "list_reply":
                incoming_message = message["interactive"]["list_reply"]["title"]
            else:
                logger.info(f"Interactive message type not supported: {message}")
                post_message(phone_number_id, phone_number, "Eingabe nicht erkannt.")
        case _:
            logger.info(f"Message type not supported: {message}")
            post_message(phone_number_id, phone_number, "Eingabe nicht erkannt.")

    if phone_number and incoming_message:
        if not session.get(phone_number):
            session[phone_number] = {"state": UserState.INITIAL.value}
            logger.info(f"Sending initial message to {phone_number}")
            MessageProvider.send_inital_message(phone_number_id, phone_number)
        else:
            message_processor = MessageProcessor()
            message = message_processor.handle_message(incoming_message, phone_number, session[phone_number]["state"])

            post_message(phone_number_id, phone_number, message)
    else:
        del session[phone_number]
        post_message(phone_number_id, phone_number, "Eingabe nicht erkannt.")

    logger.info(f"Final Session: {session.get(phone_number)}")


def post_message(phone_number_id, phone_number, message):
    payload = {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "text",
        "text": {"body": message},
    }

    response = requests.post(url_for(phone_number_id), json=payload, headers=headers)
    logger.info(f"Sending response: {response.text}")
    response.raise_for_status()


class MessageProcessor:
    def __init__(self):
        self.ratingSystem = RatingSystem()

    def handle_message(self, message: str, phone_number: str, current_state: str) -> str:
        if current_state == UserState.INITIAL.value:
            return self.handle_initial_state(message, phone_number)

        elif current_state == UserState.ADD_PLAYER.value:
            return self.handle_add_player(message, phone_number)

        elif current_state == UserState.ADD_GAME.value:
            return self.handle_add_game(message, phone_number)

        elif current_state == UserState.DELETE_GAME.value:
            return self.handle_delete_game(message, phone_number)

        else:
            del session[phone_number]
            return "Eingabe nicht erkannt."

    def handle_initial_state(self, message, phone_number) -> str:
        if message == "Spieler hinzufügen":
            session[phone_number]["state"] = UserState.ADD_PLAYER.value
            return "Bitte gib deinen Namen ein."
        elif message == "Spieler löschen":
            del session[phone_number]
            try:
                name = self.ratingSystem.delete_player(phone_number)
                return f"Spieler {name} erfolgreich gelöscht."
            except RatingException as e:
                return f"Fehler: {e}"

        # Spiel
        elif message == "Spiel hinzufügen":
            session[phone_number]["state"] = UserState.ADD_GAME.value
            return "Bitte geben Sie ein was Sie machen möchten:\nSpieltyp\nSpieler A:Spieler B\nScoreA:ScoreB\n..."
        elif message == "Spiel löschen":
            session[phone_number]["state"] = UserState.DELETE_GAME.value
            return "Bitte geben Sie die ID des Spiels ein, das Sie löschen möchten."

        # Rating
        elif message == "Rating hinzufügen":
            del session[phone_number]
            try:
                self.ratingSystem.add_player_to_rating(phone_number)
                return f"Du wurdest zu Rating hinzugefügt."
            except RatingException as e:
                return f"Fehler: {e}"
        elif message == "Rating anschauen":
            del session[phone_number]
            return self.ratingSystem.rating_image()

    def handle_add_player(self, name, phone_number):
        del session[phone_number]
        try:
            self.ratingSystem.add_player(name, phone_number)
            return f"Spieler {name} wurde hinzugefügt."
        except RatingException as e:
            return f"Fehler: {e}"

    def handle_add_game(self, message, phone_number):
        del session[phone_number]
        try:
            game_type = message.split("\n")[0]
            names = message.split("\n")[1]
            nameA, nameB = names.strip().split(":")
            scores = [tuple(map(int, match)) for match in re.findall(r"\b(\d+):(\d+)\b", message)]

            logger.info(f"Identified matches: {game_type}, {names}, {scores}")

            ids = self.ratingSystem.add_games(nameA, nameB, scores, game_type, phone_number)

            if not ids:
                return "Keine Spiele hinzugefügt."
            elif len(ids) == 1:
                return "Spiel hinzugefügt. ID: " + str(ids[0])
            else:
                return "Spiele hinzugefügt. IDs: " + ", ".join(map(str, ids))
        except RatingException as e:
            return f"Fehler: {e}"
        except Exception as e:
            return f"Fehler: {e}"

    def handle_delete_game(self, message, phone_number):
        del session[phone_number]
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
