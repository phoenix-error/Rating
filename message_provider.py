from os import environ


class MessageProvider:

    @staticmethod
    def send_interactive_message(phone_number_id, phone_number):
        url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"
        headers = {"Authorization": f"Bearer {environ['WHATSAPP_WEBHOOK_TOKEN']}", "Content-Type": "application/json"}
        payload = {
            "messaging_product": "whatsapp",
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
                            "title": "Befehle",
                            "rows": [
                                {"id": "add_player", "title": "Spieler hinzufügen"},
                                {"id": "delete_player", "title": "Spieler löschen"},
                                {"id": "add_rating", "title": "Rating hinzufügen"},
                                {"id": "view_rating", "title": "Rating anschauen"},
                                {"id": "add_game", "title": "Spiel hinzufügen"},
                                {"id": "delete_game", "title": "Spiel löschen"},
                            ],
                        }
                    ],
                },
            },
        }

        return (url, headers, payload)
