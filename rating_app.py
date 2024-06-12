import logging
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from enums import GameType
from ratingSystem import RatingSystem
import re
from waitress import serve
from exceptions import RatingException

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
    force=True,
)

app = Flask(__name__)


@app.route("/")
def test():
    return "Test"


@app.post("/whatsapp")
def whatsapp_message():
    incoming_msg = request.values.get("Body", "").strip()
    phone_number = request.values.get("From", "").strip().split(":")[-1]
    logger.debug(f"Received message: {incoming_msg} from {phone_number}")

    message_processor = MessageProcessor()
    message = message_processor.process_message(incoming_msg, phone_number)
    return str(create_response(message))


def create_response(message):
    response = MessagingResponse()
    response.message(message)
    return response


class MessageProcessor:
    def __init__(self):
        self.ratingSystem = RatingSystem()

    def process_message(self, message, phone_number) -> str:
        print(message)
        if message.lower() == "rating":
            return self.ratingSystem.rating_image()

        if message.lower().startswith(
            "löschen",
        ):
            matcher = re.match(r"löschen:\b+(\d+)\s*", message)
            if matcher:
                try:
                    self.ratingSystem.delete_game(int(matcher.group(1)))
                    return "Spiel wurde gelöscht."
                except RatingException as e:
                    return f"Fehler: {e}"
            return "Fehler: Bitte überprüfe die Eingabe.\nFormat: Löschen <id>"

        if message.lower() == "spieler löschen":
            try:
                self.ratingSystem.delete_player(phone_number)
                return f"Spieler wurde gelöscht."
            except RatingException as e:
                return f"Fehler: {e}"

        if message.lower().startswith("spieler hinzufügen"):
            pattern = r"spieler hinzufügen: ([a-zA-Z ,.'-]+)\n([a-zA-Z'-]+)\n*([a-zA-Z]+)?"
            match = re.search(pattern, message, re.IGNORECASE)
            try:
                if match:
                    name = match.group(1)
                    country = match.group(2)
                    liga = match.group(3)

                    logger.info(f"Identified matches: {name}, {country}, {liga}")
                else:
                    return f"Spieler konnte nicht hinzugefügt werden.\nBitte Eingabe überprüfen\nSpieler hinzufügen: <name>\n<country>\n<liga>(optional)"

                if not liga:
                    self.ratingSystem.add_player(name, phone_number, country)
                else:
                    self.ratingSystem.add_player(name, phone_number, country, liga)
                return f"Spieler {name} wurde hinzugefügt."
            except RatingException as e:
                return f"Fehler: {e}"

        if message.lower() == "rating hinzufügen":
            try:
                self.ratingSystem.add_player_to_rating(phone_number)
                return f"Du wurdest zum Rating hinzugefügt."
            except RatingException as e:
                return f"Fehler: {e}"

        # Message must be a game
        if message.startswith(tuple(GameType.get_values())):
            try:
                game_type = message.split("\n")[0]
                names = message.split("\n")[1]
                scores = [tuple(map(int, match)) for match in re.findall(r"\b(\d+):(\d+)\b", message)]

                ids = self.ratingSystem.add_games(names[0].strip(), names[1].strip(), scores, game_type)

                return "Spiele hinzugefügt. IDs: " + ", ".join(map(str, ids))
            except RatingException as e:
                return f"Fehler: {e}"
            except Exception as e:
                return f"Fehler: {e}"

        return "Fehler: Eingabe konnte nicht zugeordnet werden. Für mehr Informationen bitte in die Beschreibung schauen."


if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=8080)
