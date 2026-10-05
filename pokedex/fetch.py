import json

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from pokedex.config import (
    BASE_URL,
    MOVES_CACHE_PATH,
    POKEMON_CACHE_PATH,
    REQUEST_TIMEOUT,
    RETRY_BACKOFF,
    RETRY_STATUSES,
    RETRY_TOTAL,
    SMOGON_PATH,
)
from pokedex.config import TYPE_CHART_PATH as DATA_PATH
from pokedex.types import JSON, MoveCache, PokemonCache, TypeChart, UsageData

_session = requests.Session()
_session.mount(
    "https://",
    HTTPAdapter(
        max_retries=Retry(
            total=RETRY_TOTAL,
            backoff_factor=RETRY_BACKOFF,
            status_forcelist=RETRY_STATUSES,
            allowed_methods=("GET",),
        )
    ),
)


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


def load_type_chart() -> TypeChart:
    """Download the 18-type chart once and save it locally."""
    DATA_PATH.parent.mkdir(exist_ok=True)

    if DATA_PATH.exists():
        with DATA_PATH.open("r", encoding="utf-8") as file:
            cached: TypeChart = json.load(file)
        return cached

    type_chart: TypeChart = {}

    for type_name in TYPE_NAMES:
        response = _session.get(f"{BASE_URL}/type/{type_name}", timeout=REQUEST_TIMEOUT)
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
    response = _session.get(
        f"{BASE_URL}/pokemon/{pokemon_name.lower().strip()}",
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    type_entries = response.json()["types"]
    return [entry["type"]["name"] for entry in type_entries]


def get_all_pokemon_names() -> list[str]:
    """Return every Pokémon name PokeAPI knows, including forms."""
    response = _session.get(f"{BASE_URL}/pokemon?limit=100000", timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return sorted(item["name"] for item in response.json()["results"])


def get_stats(pokemon_name: str) -> dict[str, int]:
    """Return base stats, e.g. {'hp': 91, 'attack': 134, ..., 'speed': 80}."""
    response = _session.get(
        f"{BASE_URL}/pokemon/{pokemon_name.lower().strip()}",
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return {s["stat"]["name"]: s["base_stat"] for s in response.json()["stats"]}


def get_sprite(pokemon_name: str) -> str | None:
    """Return the URL of a Pokémon's front sprite, or None if PokeAPI has none."""
    response = _session.get(
        f"{BASE_URL}/pokemon/{pokemon_name.lower().strip()}",
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data: JSON = response.json()
    url: str | None = data["sprites"]["front_default"]
    return url


def get_learnable_moves(pokemon_name: str) -> list[str]:
    """Every move this Pokémon can learn, sorted."""
    response = _session.get(
        f"{BASE_URL}/pokemon/{pokemon_name.lower().strip()}",
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return sorted(m["move"]["name"] for m in response.json()["moves"])


def load_pokemon_cache() -> PokemonCache:
    """Locally saved types + stats for every Pokémon (built by scripts/build_pokemon_cache.py)."""
    with POKEMON_CACHE_PATH.open(encoding="utf-8") as f:
        data: PokemonCache = json.load(f)
    return data


def load_move_cache() -> MoveCache:
    """Locally saved type/damage_class/power for every move."""
    with MOVES_CACHE_PATH.open(encoding="utf-8") as f:
        data: MoveCache = json.load(f)
    return data


def load_smogon_usage() -> UsageData:
    """Saved Smogon top-30 usage: month, format, and ranked list."""
    with SMOGON_PATH.open(encoding="utf-8") as f:
        data: UsageData = json.load(f)
    return data
