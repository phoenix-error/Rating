class PlayerNotFoundException(Exception):
    """Exception raised for errors in the Rating System."""

    def __init__(self, location:str, *args:str):
        super().__init__(f"Spieler {", ".join(list(args))} nicht in der Datenbank gefunden.")


class PlayerAlreadyExistsException(Exception):
    """Exception raised for errors in the Rating System."""

    def __init__(self, *args:str):
        super().__init__(f"Spieler {", ".join(list(args))} existier{"en" if len(args) > 1  else "t"} bereits in der Datenbank.")
        
class PlayerNotInRatingException(Exception):
    """Exception raised for errors in the Rating System."""

    def __init__(self, *args:str):
        super().__init__(f"Spieler {", ".join(list(args))} nicht im Rating gefunden.")
        
class PlayerAlreadyInRatingException(Exception):
    """Exception raised for errors in the Rating System."""

    def __init__(self, *args:str):
        super().__init__(f"Spieler {", ".join(list(args))} existier{"en" if len(args) > 1  else "t"} bereits im Rating.")

class GameNotFoundException(Exception):
    """Exception raised for errors in the Rating System."""

    def __init__(self, game_id: int):
        super().__init__(f"Spiel {game_id} nicht in der Datenbank gefunden.")
        self.game_id = game_id
class GameTypeNotSupportedException(Exception):
    """Exception raised for errors in the Rating System."""

    def __init__(self, game_type: str):
        super().__init__(f"Spieltyp {game_type} nicht unterstützt.")
        self.game_type = game_type


class PlayerNotInGameException(Exception):
    """Exception raised for errors in the Rating System."""

    def __init__(self):
        super().__init__(f"Du kannst nur Spiele hinzufügen, in denen du mitspielst.")
