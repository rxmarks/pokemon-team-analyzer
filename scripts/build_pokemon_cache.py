import json
import time

import requests

from pokedex.fetch import BASE_URL, get_all_pokemon_names

OUT_PATH = "data/pokemon.json"


def main() -> None:
    try:
        with open(OUT_PATH, encoding="utf-8") as f:
            cache = json.load(f)
    except FileNotFoundError:
        cache = {}

    names = get_all_pokemon_names()
    for i, name in enumerate(names, start=1):
        if name in cache:
            continue
        r = requests.get(f"{BASE_URL}/pokemon/{name}", timeout=20)
        if r.status_code != 200:
            print(f"skipped {name} ({r.status_code})")
            continue
        data = r.json()
        cache[name] = {
            "types": [t["type"]["name"] for t in data["types"]],
            "stats": {s["stat"]["name"]: s["base_stat"] for s in data["stats"]},
        }
        if i % 100 == 0:
            print(f"{i}/{len(names)}")
            with open(OUT_PATH, "w", encoding="utf-8") as f:
                json.dump(cache, f)
        time.sleep(0.05)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f)
    print(f"Saved {len(cache)} Pokémon to {OUT_PATH}")


if __name__ == "__main__":
    main()
