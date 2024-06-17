from os import environ
import requests
from dotenv import load_dotenv

load_dotenv()


class MessageProvider:

    url_for = lambda phone_number_id: f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {environ['WHATSAPP_TOKEN']}",
        "Content-Type": "application/json",
    }

    @staticmethod
    def send_inital_message(phone_number_id, phone_number):
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone_number,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {"type": "text", "text": "Was möchtest du tun?"},
                "body": {"text": "Wähle eine Option"},
                "footer": {"text": ""},
                "action": {
                    "button": "Zeige Befehle",
                    "sections": [
                        {
                            "title": "Spieler",
                            "rows": [
                                {"id": "add_player", "title": "Spieler hinzufügen", "description": ""},
                                {"id": "delete_player", "title": "Spieler löschen", "description": ""},
                            ],
                        },
                        {
                            "title": "Rating",
                            "rows": [
                                {"id": "add_rating", "title": "Rating hinzufügen", "description": ""},
                                {"id": "view_rating", "title": "Rating anschauen", "description": ""},
                            ],
                        },
                        {
                            "title": "Spiel",
                            "rows": [
                                {"id": "add_game", "title": "Spiel hinzufügen", "description": ""},
                                {"id": "delete_game", "title": "Spiel löschen", "description": ""},
                            ],
                        },
                    ],
                },
            },
        }

        response = requests.post(MessageProvider.url_for(phone_number_id), json=payload, headers=MessageProvider.headers)
        response.raise_for_status()

    @staticmethod
    def send_game_flow_message(phone_number_id, phone_number):
        # TODO: Implement
        payload = {}

        response = requests.post(MessageProvider.url_for(phone_number_id), json=payload, headers=MessageProvider.headers)
        response.raise_for_status()
