from enum import IntEnum, Enum


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
