from os import environ
import requests


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
    def send_confirmation_message(phone_number_id, phone_number, message):
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone_number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "header": "Ist das korrekt?",
                "body": {"text": message},
                "footer": {"text": "<FOOTER_TEXT>"},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": "yes", "title": "Ja"}},
                        {"type": "reply", "reply": {"id": "no", "title": "Nein"}},
                    ]
                },
            },
        }

        response = requests.post(MessageProvider.url_for(phone_number_id), json=payload, headers=MessageProvider.headers)
        response.raise_for_status()
