import time

from pokedex.analysis import suggest_swaps
from pokedex.fetch import load_pokemon_cache, load_type_chart

TEAM = {
    "dragonite": ["dragon", "flying"],
    "gyarados": ["water", "flying"],
    "garchomp": ["dragon", "ground"],
    "ferrothorn": ["grass", "steel"],
    "togekiss": ["fairy", "flying"],
    "tyranitar": ["rock", "dark"],
}

chart = load_type_chart()
candidates = {n: d["types"] for n, d in load_pokemon_cache().items()}

start = time.perf_counter()
result = suggest_swaps(TEAM, candidates, chart)
elapsed = time.perf_counter() - start

print(f"{len(candidates)} candidates in {elapsed:.2f} s")
print(result.to_string())
