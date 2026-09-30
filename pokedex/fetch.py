from pathlib import Path
import json

import requests

BASE_URL = "https://pokeapi.co/api/v2"
DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "types.json"

TYPE_NAMES = [
    "normal",
    "fire",
    "water",
    "electric",
    "grass",
    "ice",
    "fighting",
    "poison",
    "ground",
    "flying",
    "psychic",
    "bug",
    "rock",
    "ghost",
    "dragon",
    "dark",
    "steel",
    "fairy",
]


def load_type_chart() -> dict:
    """Download the 18-type chart once and save it locally."""
    DATA_PATH.parent.mkdir(exist_ok=True)

    if DATA_PATH.exists():
        with DATA_PATH.open("r", encoding="utf-8") as file:
            return json.load(file)

    type_chart = {}

    for type_name in TYPE_NAMES:
        response = requests.get(f"{BASE_URL}/type/{type_name}", timeout=20)
        response.raise_for_status()

        relations = response.json()["damage_relations"]
        type_chart[type_name] = {
            relation_name: [item["name"] for item in related_types]
            for relation_name, related_types in relations.items()
        }

    with DATA_PATH.open("w", encoding="utf-8") as file:
        json.dump(type_chart, file, indent=2)

    return type_chart


def get_types(pokemon_name: str) -> list[str]:
    """Return a Pokémon's one or two types from PokeAPI."""
    response = requests.get(
        f"{BASE_URL}/pokemon/{pokemon_name.lower().strip()}",
        timeout=20,
    )
    response.raise_for_status()

    type_entries = response.json()["types"]
    return [entry["type"]["name"] for entry in type_entries]