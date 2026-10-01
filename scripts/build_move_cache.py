import json
import time

import requests

from pokedex.fetch import BASE_URL

OUT_PATH = "data/moves.json"


def main() -> None:
    try:
        with open(OUT_PATH, encoding="utf-8") as f:
            cache = json.load(f)
    except FileNotFoundError:
        cache = {}

    listing = requests.get(f"{BASE_URL}/move?limit=100000", timeout=20).json()["results"]
    for i, item in enumerate(listing, start=1):
        name = item["name"]
        if name in cache:
            continue
        r = requests.get(f"{BASE_URL}/move/{name}", timeout=20)
        if r.status_code != 200:
            print(f"skipped {name} ({r.status_code})")
            continue
        data = r.json()
        cache[name] = {
            "type": data["type"]["name"],
            "damage_class": data["damage_class"]["name"] if data["damage_class"] else "status",
            "power": data["power"],
        }
        if i % 100 == 0:
            print(f"{i}/{len(listing)}")
            with open(OUT_PATH, "w", encoding="utf-8") as f:
                json.dump(cache, f)
        time.sleep(0.05)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f)
    print(f"Saved {len(cache)} moves to {OUT_PATH}")


if __name__ == "__main__":
    main()
