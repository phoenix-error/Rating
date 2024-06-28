from enum import Enum, IntEnum


# class syntax
class Liga(IntEnum):
    LANDESLIGA = 20
    BEZIRKSLIGA = 15
    KREISLIGA = 10
    KREISKLASSE = 5
    KEINE = 0

    @staticmethod
    def get_values():
        return [game.value for game in GameType]


class GameType(Enum):
    NORMAL = "Normal"
    STRAIGHT = "14.1"

    @staticmethod
    def get_values():
        return [game.value for game in GameType]


class UserState(Enum):
    INITIAL = "initial"
    ADMIN = "admin"

    ADD_PLAYER = "add_player"

    ADD_TOURNAMENT = "add_tournament"
    ADD_GAME = "add_game"
    DELETE_GAME = "delete_game"

    ADMIN_ADD_PLAYER = "admin_add_player"
    ADMIN_DELETE_PLAYER = "admin_delete_player"
    ADMIN_ADJUST_RATING = "admin_adjust_rating"
