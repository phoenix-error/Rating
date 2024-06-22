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
                            "title": "Rating",
                            "rows": [
                                {
                                    "id": "view_rating",
                                    "title": "Rating anschauen",
                                    "description": "Schickt dir ein Bild mit dem aktuellen Rating",
                                },
                            ],
                        },
                        {
                            "title": "Spiel",
                            "rows": [
                                {"id": "add_game", "title": "Spiel hinzufügen", "description": "Fügt ein Spiel hinzu"},
                                {"id": "delete_game", "title": "Spiel löschen", "description": "Löscht ein Spiel"},
                            ],
                        },
                        {
                            "title": "Spieler",
                            "rows": [
                                {
                                    "id": "add_player",
                                    "title": "Spieler hinzufügen",
                                    "description": "Fügt einen Spieler hinzu und fügt ihn dem Rating hinzu",
                                },
                                {
                                    "id": "delete_player",
                                    "title": "Spieler löschen",
                                    "description": "Löscht einen Spieler aus dem Rating und dem System",
                                },
                            ],
                        },
                    ],
                },
            },
        }

        response = requests.post(MessageProvider.url_for(phone_number_id), json=payload, headers=MessageProvider.headers)
        response.raise_for_status()

    @staticmethod
    def send_admin_list(phone_number_id, phone_number):
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
                            "title": "Backup",
                            "rows": [
                                {
                                    "id": "backup",
                                    "title": "Backup erstellen",
                                    "description": "Erstellt ein Backup der Datenbank",
                                },
                            ],
                        },
                        {
                            "title": "Rating",
                            "rows": [
                                {
                                    "id": "adjust_rating",
                                    "title": "Rating anpassen",
                                    "description": "Passt das Rating eines Spielers an",
                                },
                            ],
                        },
                        {
                            "title": "Spieler",
                            "rows": [
                                {
                                    "id": "add_player",
                                    "title": "Spieler hinzufügen",
                                    "description": "Fügt einen Spieler zum System und Rating hinzu",
                                },
                                {
                                    "id": "delete_player",
                                    "title": "Spieler löschen",
                                    "description": "Löscht einen Spieler aus dem Rating und dem System",
                                },
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

    @staticmethod
    def send_image(phone_number_id, phone_number, url):
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone_number,
            "type": "image",
            "image": {"link": url},
        }

        response = requests.post(MessageProvider.url_for(phone_number_id), json=payload, headers=MessageProvider.headers)
        response.raise_for_status()

    @staticmethod
    def send_message(phone_number_id, phone_number, message):
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "text",
            "text": {"body": message},
        }

        response = requests.post(MessageProvider.url_for(phone_number_id), json=payload, headers=MessageProvider.headers)
        response.raise_for_status()
