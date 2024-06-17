import re
import pandas as pd
from rating_system import RatingSystem
from exceptions import (
    PlayerAlreadyExistsException,
    PlayerNotFoundException,
    PlayerNotInRatingException,
    PlayerAlreadyInRatingException,
)


def add_players_to_rating(file_path):
    with open(file_path, "r") as file:
        content = file.read()

    pattern = re.compile(r"([a-zA-ZäöüÄÖÜß, ]+)\n(\d+)")
    matches = pattern.findall(content)

    ratingSystem = RatingSystem()
    for match in matches:
        name = match[0].strip()
        phone_number = match[1].strip()

        try:
            ratingSystem.add_player(name, phone_number)
        except PlayerAlreadyExistsException as e:
            print(f"Fehler: {e}")

        try:
            ratingSystem.add_player_to_rating(phone_number)
        except PlayerAlreadyInRatingException as e:
            print(f"Fehler: {e}")


ratingSystem = RatingSystem()
file_path = "./manual_input/names.txt"
# add_players_to_rating(file_path)

data = pd.read_excel(
    "./manual_input/rating.xlsx",
)

# Extract name, rating, games_won, games_lost from data
for index, row in data.iterrows():
    name = row["Name"]
    rating = row["Rating"]
    games_won = row["Gewonnen"]
    games_lost = row["Verloren"]
    try:
        ratingSystem.adjust_rating(name, rating, games_won, games_lost)
        print("\n")
    except PlayerNotFoundException as e:
        print(f"Fehler:\n{e}")
    except PlayerNotInRatingException as e:
        print(f"Fehler:\n{e}")
