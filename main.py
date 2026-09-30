from pokedex.analysis import coverage_gaps, multiplier, team_table
from pokedex.fetch import get_types, load_type_chart
import pandas as pd
pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)

SAMPLE_TEAM = ["dragonite", "gyarados", "garchomp", "ferrothorn", "togekiss", "tyranitar"]


def main() -> None:
    type_chart = load_type_chart()

    print("Ice vs Dragonite:", multiplier("ice", ["dragon", "flying"], type_chart))
    print("Ground vs Aerodactyl:", multiplier("ground", ["rock", "flying"], type_chart))

    team = {name: get_types(name) for name in SAMPLE_TEAM}
    table = team_table(team, type_chart)
    print(table)

    print("Coverage gaps:", coverage_gaps(team, type_chart))

if __name__ == "__main__":
    main()