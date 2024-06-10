from enum import IntEnum, Enum


# class syntax
class Liga(IntEnum):
    LANDESLIGA = 20
    BEZIRKSLIGA = 15
    KREISLIGA = 10
    KREISKLASSE = 5
    KEINE = 0


class GameType(Enum):
    NORMAL = "Normal"
    STRAIGHT = "14.1"
