import logging
import re
from os import environ

import sentry_sdk
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from flask import Flask, request
from pytz import timezone
from sentry_sdk import capture_exception, set_user
from sentry_sdk.integrations.logging import LoggingIntegration
from sqlalchemy.exc import PendingRollbackError
from waitress import serve

from rating_system import RatingSystem
from utils.constants import EINGABE_NICHT_ERKANNT, HELP_COMMAND
from utils.enums import UserState
from utils.exceptions import *
from utils.message_provider import MessageProvider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    force=True,
)

sentry_logging = LoggingIntegration(level=logging.INFO, event_level=logging.CRITICAL)

load_dotenv()

sentry_sdk.init(
    dsn=environ["SENTRY_DSN"],
    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for performance monitoring.
    traces_sample_rate=1.0,
    # Set profiles_sample_rate to 1.0 to profile 100%
    # of sampled transactions.
    # We recommend adjusting this value in production.
    profiles_sample_rate=1.0,
    integrations=[sentry_logging],
)

app = Flask(__name__)
session = dict()

ratingSystem = RatingSystem()


@app.route("/")
def test():
    return "<pre>Nothing to see here.</pre>"


@app.route("/rating")
def rating():
    try:
        url = ratingSystem.rating_image()
        return f'<img src="{url}" style="display: block; margin-left: auto; margin-right: auto; height: 100%;" />'
    except Exception as e:
        capture_exception(e)
        return f"Rating konnte nicht aktualisiert werden. Wende dich an den Admin."


@app.get("/whatsapp")
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    logging.info(f"Received request with mode: {mode}, token: {token}, challenge: {challenge}")

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
    if not data.get("object") == "whatsapp_business_account":
        return {"status": "OK"}, 200

    entry = data.get("entry")
    if not entry or not entry[0].get("changes"):
        return {"status": "OK"}, 200

    change = entry[0].get("changes")[0]
    if not change or not change.get("value"):
        return {"status": "OK"}, 200

    value = change.get("value")
    if not value.get("metadata") or not value.get("messages"):
        return {"status": "OK"}, 200

    if not value["metadata"]["phone_number_id"] or not value["messages"][0]:
        return {"status": "OK"}, 200

    if value.get("contacts") and value["contacts"][0].get("profile"):
        username = value["contacts"][0]["profile"]["name"]
    else:
        username = "Unknown User"

    try:

        phone_number_id = value["metadata"]["phone_number_id"]
        message = value["messages"][0]
        phone_number = message["from"]
        set_user({"id": phone_number, "username": username})
        logging.info(f"Received message: {message} with phone number id: {phone_number_id}")

        logging.info(f"Inital Session: {session.get(phone_number)}")

        match message["type"]:
            case "text":
                incoming_message = message["text"]["body"]
            case "interactive":
                if message["interactive"]["type"] == "list_reply":
                    incoming_message = message["interactive"]["list_reply"]["title"]
                else:
                    logging.info(f"Interactive message type not supported: {message}")
                    MessageProvider.send_message(phone_number_id, phone_number, EINGABE_NICHT_ERKANNT)
            case _:
                logging.info(f"Message type not supported: {message}")
                MessageProvider.send_message(phone_number_id, phone_number, EINGABE_NICHT_ERKANNT)

        if phone_number and incoming_message:
            if not session.get(phone_number):
                session[phone_number] = {"state": UserState.INITIAL.value}

            handle_message(phone_number_id, phone_number, incoming_message, session[phone_number]["state"])
        else:
            del session[phone_number]
            MessageProvider.send_message(phone_number_id, phone_number, EINGABE_NICHT_ERKANNT)

        logging.info(f"Final Session: {session.get(phone_number)}")
        set_user(None)
        return {"status": "OK"}, 200
    except Exception as e:
        capture_exception(e)
        set_user(None)
        return {"status": "Error handling message"}, 200


def handle_message(phone_number_id, phone_number, message: str, current_state: str):
    match current_state:
        case UserState.ADMIN.value:
            handle_admin_message(message.replace("admin", "").strip(), phone_number_id, phone_number)
        case UserState.INITIAL.value:
            handle_initial_state(message, phone_number_id, phone_number)
        case UserState.ADD_PLAYER.value:
            handle_add_player(message, phone_number_id, phone_number)
        case UserState.ADD_GAME.value:
            handle_add_game(message, phone_number_id, phone_number)
        case UserState.DELETE_GAME.value:
            handle_delete_game(message, phone_number_id, phone_number)
        case _:
            session.pop(phone_number, None)
            MessageProvider.send_message(phone_number_id, phone_number, EINGABE_NICHT_ERKANNT)


def handle_initial_state(message, phone_number_id, phone_number):
    match message:
        case "admin" | "Admin":
            if phone_number != environ["ADMIN_PHONE_NUMBER"]:
                MessageProvider.send_message(
                    phone_number_id, phone_number, "Du hast keine Berechtigung, diese Aktion auszuführen."
                )
                return
            session[phone_number]["state"] = UserState.ADMIN.value
            MessageProvider.send_message(phone_number_id, phone_number, "Bitte geben Sie das Admin-Kommando ein.")
        case "start" | "Start":
            logging.info(f"Sending initial message to {phone_number}")
            MessageProvider.send_inital_message(phone_number_id, phone_number)
        case "Spieler hinzufügen":
            session[phone_number]["state"] = UserState.ADD_PLAYER.value
            MessageProvider.send_message(phone_number_id, phone_number, "Bitte geben Sie den Namen des Spielers ein.")
        case "Spieler löschen":
            session.pop(phone_number, None)
            try:
                name = ratingSystem.delete_player(phone_number)
                MessageProvider.send_message(phone_number_id, phone_number, f"Spieler {name} erfolgreich gelöscht.")
            except PlayerNotFoundException as e:
                capture_exception(e)
                MessageProvider.send_message(phone_number_id, phone_number, f"Fehler: {e}")
        case "Spiel hinzufügen":
            session[phone_number]["state"] = UserState.ADD_GAME.value
            MessageProvider.send_message(
                phone_number_id,
                phone_number,
                "Bitte geben Sie das Spiel im folgenden Format ein:\n\nSpieltyp\nSpieler A: Spieler B\nScore A: Score B\nScore A: Score B\n...",
            )
        case "Spiel löschen":
            session[phone_number]["state"] = UserState.DELETE_GAME.value
            MessageProvider.send_message(
                phone_number_id, phone_number, "Bitte geben Sie die ID des Spiels ein, das Sie löschen möchten."
            )
        case "Rating anschauen":
            session.pop(phone_number, None)
            try:
                url = ratingSystem.rating_image()
                MessageProvider.send_image(phone_number_id, phone_number, url)
            except Exception as e:
                capture_exception(e)
                MessageProvider.send_message(
                    phone_number_id,
                    phone_number,
                    f"Rating konnte nicht aktualisiert werden. Wende dich an den Admin.",
                )
        case "hilfe" | "Hilfe":
            session.pop(phone_number, None)
            MessageProvider.send_message(
                phone_number_id,
                phone_number,
                HELP_COMMAND,
            )
        case _:
            session.pop(phone_number, None)
            MessageProvider.send_message(
                phone_number_id,
                phone_number,
                EINGABE_NICHT_ERKANNT,
            )


def handle_add_player(name, phone_number_id, phone_number):
    session.pop(phone_number, None)
    try:
        ratingSystem.add_player(name, phone_number)
        ratingSystem.add_player_to_rating(phone_number)
        MessageProvider.send_message(phone_number_id, phone_number, f"Spieler {name} erfolgreich hinzugefügt.")
    except PlayerAlreadyExistsException as e:
        MessageProvider.send_message(phone_number_id, phone_number, f"Fehler: {e}")
    except PlayerNotFoundException as e:
        MessageProvider.send_message(phone_number_id, phone_number, f"Fehler: {e}")
    except PlayerAlreadyInRatingException as e:
        MessageProvider.send_message(phone_number_id, phone_number, f"Fehler: {e}")


def handle_add_game(message, phone_number_id, phone_number):
    session.pop(phone_number, None)
    try:
        game_type = message.split("\n")[0]
        names = message.split("\n")[1]
        nameA, nameB = names.strip().split(":")
        scores = [tuple(map(int, match)) for match in re.findall(r"\b(\d+)[ \t]*:[ \t]*(\d+)\b", message)]

        logging.info(f"Identified matches: {game_type}, {names}, {scores}")

        changes = ratingSystem.add_games(nameA, nameB, scores, game_type, phone_number)

        if not changes:
            MessageProvider.send_message(phone_number_id, phone_number, "Keine Spiele hinzugefügt.")
        elif len(changes) == 1:
            id, rating_change = changes[0]
            MessageProvider.send_message(
                phone_number_id, phone_number, f"Spiel hinzugefügt.\nID: {id}.\nRatingänderung: {rating_change:.2f}"
            )
        else:
            message = "Spiele hinzugefügt.\n"
            # Write scores with ids
            for i, (id, rating_change) in enumerate(changes):
                message += f"Spiel {i+1}:\nID: {id}. Änderung: {rating_change:.2f}\n"

            MessageProvider.send_message(phone_number_id, phone_number, message)
    except PlayerNotFoundException as e:
        MessageProvider.send_message(phone_number_id, phone_number, f"Fehler: {e}")
    except PlayerNotInRatingException as e:
        MessageProvider.send_message(phone_number_id, phone_number, f"Fehler: {e}")
    except GameTypeNotSupportedException as e:
        MessageProvider.send_message(phone_number_id, phone_number, f"Fehler: {e}")
    except PlayerNotInGameException as e:
        capture_exception(e)
        MessageProvider.send_message(phone_number_id, phone_number, f"Fehler: {e}")
    except PendingRollbackError as e:
        capture_exception(e)
        MessageProvider.send_message(phone_number_id, phone_number, f"Fehler: {e}")


def handle_delete_game(
    id,
    phone_number_id,
    phone_number,
):
    session.pop(phone_number, None)
    try:
        if not id.startswith("#"):
            id = f"#{id}"
        ratingSystem.delete_game(id, phone_number)
        MessageProvider.send_message(phone_number_id, phone_number, f"Spiel {id} erfolgreich gelöscht.")
    except GameNotFoundException as e:
        capture_exception(e)
        MessageProvider.send_message(phone_number_id, phone_number, f"Fehler: {e}")
    except GameTooOldException as e:
        capture_exception(e)
        MessageProvider.send_message(phone_number_id, phone_number, f"Fehler: {e}")
    except PlayerNotInGameException as e:
        capture_exception(e)
        MessageProvider.send_message(phone_number_id, phone_number, f"Fehler: {e}")


def handle_admin_message(message: str, phone_number_id: str, phone_number: str):
    session.pop(phone_number, None)
    if phone_number != environ["ADMIN_PHONE_NUMBER"]:
        MessageProvider.send_message(phone_number_id, phone_number, "Du hast keine Berechtigung, diese Aktion auszuführen.")
        return

    first_line = message.splitlines()[0].lower()
    match first_line:
        case "backup" | "export":
            export_database(phone_number_id, phone_number)
        case "adjust rating" | "adjust":
            handle_adjust_rating(message.splitlines()[1:], phone_number_id, phone_number)
        case "add player":
            name = message.splitlines()[1]
            phone_number = message.splitlines()[2]

            session.pop(phone_number, None)
            try:
                ratingSystem.add_player(name, phone_number)
                ratingSystem.add_player_to_rating(phone_number)
                MessageProvider.send_message(phone_number_id, phone_number, f"Spieler {name} erfolgreich hinzugefügt.")
            except PlayerAlreadyExistsException as e:
                capture_exception(e)
                MessageProvider.send_message(phone_number_id, phone_number, f"Fehler: {e}")
            except PlayerNotFoundException as e:
                capture_exception(e)
                MessageProvider.send_message(phone_number_id, phone_number, f"Fehler: {e}")
            except PlayerAlreadyInRatingException as e:
                capture_exception(e)
                MessageProvider.send_message(phone_number_id, phone_number, f"Fehler: {e}")
        case "delete player":
            handle_delete_player(message.splitlines()[1], phone_number_id, phone_number)
        case _:
            MessageProvider.send_message(phone_number_id, phone_number, "Admin Command nicht erkannt.")


def handle_delete_player(name: str, phone_number_id: str, phone_number: str):
    session.pop(phone_number, None)
    try:
        ratingSystem.delete_player(phone_number, name=name)
        MessageProvider.send_message(phone_number_id, phone_number, f"Spieler {name} erfolgreich gelöscht.")
    except PlayerNotFoundException as e:
        capture_exception(e)
        MessageProvider.send_message(phone_number_id, phone_number, f"Fehler: {e}")


def handle_adjust_rating(lines: list[str], phone_number_id: str, phone_number: str):
    session.pop(phone_number, None)
    try:
        name = lines[0]
        rating = float(lines[1])
        games_won = int(lines[2])
        games_lost = int(lines[3])
        ratingSystem.adjust_rating(name, rating, games_won, games_lost)
        MessageProvider.send_message(phone_number_id, phone_number, f"Rating für {name} erfolgreich angepasst.")
    except PlayerNotFoundException as e:
        capture_exception(e)
        MessageProvider.send_message(phone_number_id, phone_number, f"Fehler: {e}")
    except PlayerNotInRatingException as e:
        capture_exception(e)
        MessageProvider.send_message(phone_number_id, phone_number, f"Fehler: {e}")
    except ValueError as e:
        capture_exception(e)
        MessageProvider.send_message(phone_number_id, phone_number, f"Fehler: {e}")


# Scheduler Jobs


def export_database(phone_number_id=None, phone_number=None):
    try:
        ratingSystem.export_database()
        if phone_number_id and phone_number:
            MessageProvider.send_message(phone_number_id, phone_number, "Database exported successfully.")
        return "Database exported successfully."
    except Exception as e:
        capture_exception(e)
        if phone_number_id and phone_number:
            MessageProvider.send_message(phone_number_id, phone_number, "Error exporting database.")
        return "Error exporting database."


def apply_rating_decay():
    try:
        ratingSystem.apply_rating_decay()
        return "Rating decay applied successfully."
    except Exception as e:
        capture_exception(e)
        return "Error applying rating decay."


if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=export_database, trigger="interval", hours=1)
    scheduler.add_job(func=apply_rating_decay, trigger=CronTrigger(hour=8, minute=0, timezone=timezone("Europe/Berlin")))
    scheduler.start()

    try:
        serve(app, host="0.0.0.0", port=8080)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
