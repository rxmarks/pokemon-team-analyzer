import pandas as pd

from pokedex.analysis import coverage_gaps, multiplier, suggest_swaps, team_table
from pokedex.fetch import get_types, load_type_chart

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)

SAMPLE_TEAM = ["dragonite", "gyarados", "garchomp", "ferrothorn", "togekiss", "tyranitar"]

CANDIDATES = [
    "lucario", "metagross", "scizor", "heatran", "magnezone",
    "azumarill", "clefable", "conkeldurr", "excadrill", "empoleon",
    "blissey", "skarmory", "corviknight", "breloom", "infernape",
    "weavile", "gengar", "volcarona", "hydreigon", "rotom-wash",
]


def main() -> None:
    type_chart = load_type_chart()

    print("Ice vs Dragonite:", multiplier("ice", ["dragon", "flying"], type_chart))
    print("Ground vs Aerodactyl:", multiplier("ground", ["rock", "flying"], type_chart))

    team = {name: get_types(name) for name in SAMPLE_TEAM}
    table = team_table(team, type_chart)
    print(table.to_string())

    print("Coverage gaps:", coverage_gaps(team, type_chart))

    candidates = {name: get_types(name) for name in CANDIDATES}
    print("\nTop swap suggestions:")
    print(suggest_swaps(team, candidates, type_chart).to_string())


if __name__ == "__main__":
    main()