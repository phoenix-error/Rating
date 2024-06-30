import os
import sys
from dataclasses import dataclass

import pytest

# getting the name of the directory
# where the this file is present.
current = os.path.dirname(os.path.realpath(__file__))

# Getting the parent directory name
# where the current directory is present.
parent = os.path.dirname(current)

# adding the parent directory to
# the sys.path.
sys.path.append(parent)

from rating_system import PlayerAlreadyExistsException, PlayerNotFoundException, RatingSystem


@dataclass
class Player:
    name: str
    phone_number: str


playerA = Player("Horst, Streit", "1234567890")
playerB = Player("Maximilian, Win", "0987654321")


@pytest.fixture
def rating_system():
    return RatingSystem()


def test_add_player(rating_system):
    (name, phone_number) = (playerA.name, playerA.phone_number)
    rating_system.add_player(name, phone_number)
    assert name in rating_system.get_names()
    (name, phone_number) = (playerB.name, playerB.phone_number)
    rating_system.add_player(name, phone_number)
    assert name in rating_system.get_names()


def test_add_existing_player_raises_exception(rating_system):
    (name, phone_number) = (playerA.name, playerA.phone_number)
    rating_system.add_player(name, phone_number)
    with pytest.raises(PlayerAlreadyExistsException):
        rating_system.add_player(name, phone_number)


def test_delete_player(rating_system):
    (name, phone_number) = (playerA.name, playerA.phone_number)
    rating_system.add_player(name, phone_number)
    assert name in rating_system.get_names()
    rating_system.delete_player(phone_number)
    assert name not in rating_system.get_names()


def test_delete_player_raises_exception_for_unknown_player(rating_system):
    with pytest.raises(PlayerNotFoundException):
        rating_system.delete_player(playerB.phone_number)


def test_add_player_to_rating(rating_system):
    rating_system.add_player_to_rating(playerA.phone_number)
    rating_system.add_player_to_rating(playerB.phone_number)


def test_find_closest_name(rating_system):
    closest_name = rating_system.find_closest_name(playerA.name[1:])
    assert closest_name == playerA.name


def test_add_game(rating_system):
    ratingA = rating_system.get_rating(playerA.name)
    ratingB = rating_system.get_rating(playerB.name)

    game_id, rating_change = rating_system.add_game(playerA.name, playerB.name, 10, 5, "Normal", playerA.phone_number)

    assert game_id is not None
    assert rating_change is not None
    assert ratingA + rating_change == rating_system.get_rating(playerA.name)
    assert ratingB - rating_change == rating_system.get_rating(playerB.name)


def test_add_and_delete_game(rating_system):
    ratingA = rating_system.get_rating(playerA.name)
    ratingB = rating_system.get_rating(playerB.name)

    game_id, rating_change = rating_system.add_game(playerA.name, playerB.name, 10, 5, "Normal", playerA.phone_number)

    after_insert_ratingA = rating_system.get_rating(playerA.name)
    after_insert_ratingB = rating_system.get_rating(playerB.name)

    assert after_insert_ratingA == ratingA + rating_change
    assert after_insert_ratingB == ratingB - rating_change

    rating_system.delete_game(game_id, playerA.phone_number)

    assert rating_system.get_rating(playerA.name) == ratingA
    assert rating_system.get_rating(playerB.name) == ratingB


def test_adjust_rating(rating_system):
    rating_system.adjust_rating(playerA.name, 50.0, 0, 0, "4915906837885")

    assert rating_system.get_rating(playerA.name) == 50.0


def test_rating_decay(rating_system):
    rating_system.apply_rating_decay()


def test_export_database(rating_system):
    rating_system.export_database()


def test_find_closest_name_raises_exception_for_no_match(rating_system):
    with pytest.raises(PlayerNotFoundException):
        rating_system.find_closest_name("Unbekannter Name")
