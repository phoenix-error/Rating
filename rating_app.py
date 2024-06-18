import logging
from flask import Flask, request, jsonify
import re
from waitress import serve
from exceptions import *
from os import urandom, environ
from enum import Enum
from rating_system import RatingSystem
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
                            return {"status": "Error handling message"}, 200

    return {"status": "OK"}, 200


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
                MessageProvider.send_message(phone_number_id, phone_number, "Eingabe nicht erkannt.")
        case _:
            logger.info(f"Message type not supported: {message}")
            MessageProvider.send_message(phone_number_id, phone_number, "Eingabe nicht erkannt.")

    if phone_number and incoming_message:
        if not session.get(phone_number):
            session[phone_number] = {"state": UserState.INITIAL.value}
            logger.info(f"Sending initial message to {phone_number}")
            MessageProvider.send_inital_message(phone_number_id, phone_number)
        else:
            message_processor = MessageProcessor(phone_number_id, phone_number)
            message_processor.handle_message(incoming_message, session[phone_number]["state"])
    else:
        del session[phone_number]
        MessageProvider.send_message(phone_number_id, phone_number, "Eingabe nicht erkannt.")

    logger.info(f"Final Session: {session.get(phone_number)}")


class MessageProcessor:
    def __init__(self, phone_number_id, phone_number):
        self.ratingSystem = RatingSystem()
        self.phone_number_id = phone_number_id
        self.phone_number = phone_number

    def handle_message(self, message: str, current_state: str):
        match current_state:
            case UserState.INITIAL.value:
                return self.handle_initial_state(message)
            case UserState.ADD_PLAYER.value:
                return self.handle_add_player(name=message)
            case UserState.ADD_GAME.value:
                return self.handle_add_game(message)
            case UserState.DELETE_GAME.value:
                return self.handle_delete_game(id=message)
            case _:
                del session[self.phone_number]
                MessageProvider.send_message(self.phone_number_id, self.phone_number, "Eingabe nicht erkannt.")

    def handle_initial_state(self, message):
        match message:
            case "Spieler hinzufügen":
                session[self.phone_number]["state"] = UserState.ADD_PLAYER.value
                MessageProvider.send_message(
                    self.phone_number_id, self.phone_number, "Bitte geben Sie den Namen des Spielers ein."
                )
            case "Spieler löschen":
                del session[self.phone_number]
                try:
                    name = self.ratingSystem.delete_player(self.phone_number)
                    MessageProvider.send_message(self.phone_number_id, self.phone_number, f"Spieler {name} erfolgreich gelöscht.")
                except PlayerNotFoundException as e:
                    MessageProvider.send_message(self.phone_number_id, self.phone_number, f"Fehler: {e}")
            case "Spiel hinzufügen":
                session[self.phone_number]["state"] = UserState.ADD_GAME.value
                MessageProvider.send_message(
                    self.phone_number_id,
                    self.phone_number,
                    "Bitte geben Sie ein was Sie machen möchten:\nSpieltyp\nSpieler A:Spieler B\nScoreA:ScoreB\n...",
                )
            case "Spiel löschen":
                session[self.phone_number]["state"] = UserState.DELETE_GAME.value
                MessageProvider.send_message(
                    self.phone_number_id, self.phone_number, "Bitte geben Sie die ID des Spiels ein, das Sie löschen möchten."
                )
            case "Rating anschauen":
                del session[self.phone_number]
                try:
                    url = self.ratingSystem.rating_image()
                    MessageProvider.send_image(self.phone_number_id, self.phone_number, url)
                except:
                    MessageProvider.send_message(
                        self.phone_number_id,
                        self.phone_number,
                        f"Rating konnte nicht aktualisiert werden. Wende dich an den Admin.",
                    )

    def handle_add_player(self, name):
        del session[self.phone_number]
        try:
            self.ratingSystem.add_player(name, self.phone_number)
            self.ratingSystem.add_player_to_rating(self.phone_number)
            MessageProvider.send_message(self.phone_number_id, self.phone_number, f"Spieler {name} erfolgreich hinzugefügt.")
        except PlayerAlreadyExistsException as e:
            MessageProvider.send_message(self.phone_number_id, self.phone_number, f"Fehler: {e}")
        except PlayerNotFoundException as e:
            MessageProvider.send_message(self.phone_number_id, self.phone_number, f"Fehler: {e}")
        except PlayerAlreadyInRatingException as e:
            MessageProvider.send_message(self.phone_number_id, self.phone_number, f"Fehler: {e}")

    def handle_add_game(self, message):
        del session[self.phone_number]
        try:
            game_type = message.split("\n")[0]
            names = message.split("\n")[1]
            nameA, nameB = names.strip().split(":")
            scores = [tuple(map(int, match)) for match in re.findall(r"\b(\d+):(\d+)\b", message)]

            logger.info(f"Identified matches: {game_type}, {names}, {scores}")

            ids = self.ratingSystem.add_games(nameA, nameB, scores, game_type, self.phone_number)

            if not ids:
                MessageProvider.send_message(self.phone_number_id, self.phone_number, "Keine Spiele hinzugefügt.")
            elif len(ids) == 1:
                MessageProvider.send_message(self.phone_number_id, self.phone_number, f"Spiel hinzugefügt. ID: {ids[0]}")
            else:
                MessageProvider.send_message(
                    self.phone_number_id, self.phone_number, f"Spiele hinzugefügt. IDs: {', '.join(map(str, ids))}"
                )

            try:
                url = self.ratingSystem.rating_image()
                MessageProvider.send_image(self.phone_number_id, self.phone_number, url)
            except:
                MessageProvider.send_message(
                    self.phone_number_id, self.phone_number, f"Rating konnte nicht aktualisiert werden. Wende dich an den Admin."
                )
        except PlayerNotFoundException as e:
            MessageProvider.send_message(self.phone_number_id, self.phone_number, f"Fehler: {e}")
        except PlayerNotInRatingException as e:
            MessageProvider.send_message(self.phone_number_id, self.phone_number, f"Fehler: {e}")
        except PlayerNotInGameException as e:
            MessageProvider.send_message(self.phone_number_id, self.phone_number, f"Fehler: {e}")
        except GameTypeNotSupportedException as e:
            MessageProvider.send_message(self.phone_number_id, self.phone_number, f"Fehler: {e}")

    def handle_delete_game(
        self,
        id,
    ):
        del session[self.phone_number]
        try:
            id = int(id)
            self.ratingSystem.delete_game(id, self.phone_number)
            MessageProvider.send_message(self.phone_number_id, self.phone_number, f"Spiel {id} erfolgreich gelöscht.")
        except GameNotFoundException as e:
            MessageProvider.send_message(self.phone_number_id, self.phone_number, f"Fehler: {e}")
        except PlayerNotInGameException as e:
            MessageProvider.send_message(self.phone_number_id, self.phone_number, f"Fehler: {e}")


if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=8080)
