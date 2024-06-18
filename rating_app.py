import logging
from flask import Flask, request
import re
from waitress import serve
from exceptions import *
from os import environ
from enum import Enum
from rating_system import RatingSystem
from message_provider import MessageProvider
from constants import EINGABE_NICHT_ERKANNT, HELP_COMMAND
from dotenv import load_dotenv

load_dotenv()


class UserState(Enum):
    INITIAL = "initial"

    ADD_PLAYER = "add_player"

    ADD_GAME = "add_game"
    DELETE_GAME = "delete_game"


logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
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
            return {"status": "error", "message": "Verification failed"}, 403
    return {"status": "error", "message": "Missing parameters"}, 400


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
                MessageProvider.send_message(phone_number_id, phone_number, EINGABE_NICHT_ERKANNT)
        case _:
            logger.info(f"Message type not supported: {message}")
            MessageProvider.send_message(phone_number_id, phone_number, EINGABE_NICHT_ERKANNT)

    if phone_number and incoming_message:
        if not session.get(phone_number):
            session[phone_number] = {"state": UserState.INITIAL.value}

        message_processor = MessageProcessor(phone_number_id, phone_number)
        message_processor.handle_message(incoming_message, session[phone_number]["state"])
    else:
        del session[phone_number]
        MessageProvider.send_message(phone_number_id, phone_number, EINGABE_NICHT_ERKANNT)

    logger.info(f"Final Session: {session.get(phone_number)}")


class MessageProcessor:
    def __init__(self, phone_number_id, phone_number):
        self.ratingSystem = RatingSystem()
        self.phone_number_id = phone_number_id
        self.phone_number = phone_number

    def handle_message(self, message: str, current_state: str):
        if message.startswith("admin"):
            self.handle_admin_message(message.replace("admin", "").strip())
            return

        match current_state:
            case UserState.INITIAL.value:
                self.handle_initial_state(message)
            case UserState.ADD_PLAYER.value:
                self.handle_add_player(name=message)
            case UserState.ADD_GAME.value:
                return self.handle_add_game(message)
            case UserState.DELETE_GAME.value:
                return self.handle_delete_game(id=message)
            case _:
                session.pop(self.phone_number, None)
                MessageProvider.send_message(self.phone_number_id, self.phone_number, EINGABE_NICHT_ERKANNT)

    def handle_initial_state(self, message):
        match message:
            case "start" | "Start":
                logger.info(f"Sending initial message to {self.phone_number}")
                MessageProvider.send_inital_message(self.phone_number_id, self.phone_number)
            case "Spieler hinzufügen":
                session[self.phone_number]["state"] = UserState.ADD_PLAYER.value
                MessageProvider.send_message(
                    self.phone_number_id, self.phone_number, "Bitte geben Sie den Namen des Spielers ein."
                )
            case "Spieler löschen":
                session.pop(self.phone_number, None)
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
                    "Bitte geben Sie das Spiel im folgenden Format ein:\n\nSpieltyp\nSpieler A: Spieler B\nScore A: Score B\nScore A: Score B\n...",
                )
            case "Spiel löschen":
                session[self.phone_number]["state"] = UserState.DELETE_GAME.value
                MessageProvider.send_message(
                    self.phone_number_id, self.phone_number, "Bitte geben Sie die ID des Spiels ein, das Sie löschen möchten."
                )
            case "Rating anschauen":
                session.pop(self.phone_number, None)
                try:
                    url = self.ratingSystem.rating_image()
                    MessageProvider.send_image(self.phone_number_id, self.phone_number, url)
                except:
                    MessageProvider.send_message(
                        self.phone_number_id,
                        self.phone_number,
                        f"Rating konnte nicht aktualisiert werden. Wende dich an den Admin.",
                    )
            case "hilfe" | "Hilfe":
                session.pop(self.phone_number, None)
                MessageProvider.send_message(
                    self.phone_number_id,
                    self.phone_number,
                    HELP_COMMAND,
                )
            case _:
                session.pop(self.phone_number, None)
                MessageProvider.send_message(
                    self.phone_number_id,
                    self.phone_number,
                    EINGABE_NICHT_ERKANNT,
                )

    def handle_add_player(self, name):
        session.pop(self.phone_number, None)
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
        session.pop(self.phone_number, None)
        try:
            game_type = message.split("\n")[0]
            names = message.split("\n")[1]
            nameA, nameB = names.strip().split(":")
            scores = [tuple(map(int, match)) for match in re.findall(r"\b(\d+):(\d+)\b", message)]

            logger.info(f"Identified matches: {game_type}, {names}, {scores}")

            changes = self.ratingSystem.add_games(nameA, nameB, scores, game_type, self.phone_number)

            if not changes:
                MessageProvider.send_message(self.phone_number_id, self.phone_number, "Keine Spiele hinzugefügt.")
            elif len(changes) == 1:
                id, rating_change = changes[0]
                MessageProvider.send_message(
                    self.phone_number_id, self.phone_number, f"Spiel hinzugefügt. ID: {id}. Ratingänderung: {rating_change}"
                )
            else:
                message = "Spiele hinzugefügt.\n"
                # Write scores with ids
                for i, (id, rating_change) in enumerate(changes):
                    message += f"Spiel {i+1}: ID: {id}. Ratingänderung: {rating_change}\n"

                MessageProvider.send_message(self.phone_number_id, self.phone_number, message)

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
        session.pop(self.phone_number, None)
        try:
            self.ratingSystem.delete_game(id, self.phone_number)
            MessageProvider.send_message(self.phone_number_id, self.phone_number, f"Spiel {id} erfolgreich gelöscht.")
        except GameNotFoundException as e:
            MessageProvider.send_message(self.phone_number_id, self.phone_number, f"Fehler: {e}")
        except PlayerNotInGameException as e:
            MessageProvider.send_message(self.phone_number_id, self.phone_number, f"Fehler: {e}")

    def handle_admin_message(self, message: str):
        session.pop(self.phone_number, None)
        if self.phone_number != environ["ADMIN_PHONE_NUMBER"]:
            MessageProvider.send_message(
                self.phone_number_id, self.phone_number, "Du hast keine Berechtigung, diese Aktion auszuführen."
            )
            return

        match message.splitlines()[0]:
            case "adjust rating":
                self.handle_adjust_rating(message.splitlines()[1:])
            case _:
                MessageProvider.send_message(self.phone_number_id, self.phone_number, "Admin Command nicht erkannt.")

    def handle_adjust_rating(self, lines: list[str]):
        session.pop(self.phone_number, None)
        try:
            name = lines[0]
            rating = float(lines[1])
            games_won = int(lines[2])
            games_lost = int(lines[3])
            self.ratingSystem.adjust_rating(name, rating, games_won, games_lost)
            MessageProvider.send_message(self.phone_number_id, self.phone_number, f"Rating für {name} erfolgreich angepasst.")
        except PlayerNotFoundException as e:
            MessageProvider.send_message(self.phone_number_id, self.phone_number, f"Fehler: {e}")
        except PlayerNotInRatingException as e:
            MessageProvider.send_message(self.phone_number_id, self.phone_number, f"Fehler: {e}")
        except ValueError as e:
            MessageProvider.send_message(self.phone_number_id, self.phone_number, f"Fehler: {e}")


if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=8080)
