import pandas as pd


def multiplier(attack_type: str, defender_types: list[str], type_chart: dict) -> float:
    """Damage multiplier for one attack type against a Pokémon's types."""
    result = 1.0
    for defending_type in defender_types:
        relations = type_chart[defending_type]
        if attack_type in relations["no_damage_from"]:
            result *= 0.0
        elif attack_type in relations["double_damage_from"]:
            result *= 2.0
        elif attack_type in relations["half_damage_from"]:
            result *= 0.5
    return result

def team_table(team: dict[str, list[str]], type_chart: dict) -> pd.DataFrame:
    """Rows = attack types, columns = team members, plus weak/resist counts."""
    rows = {}
    for attack_type in type_chart:
        rows[attack_type] = {
            name: multiplier(attack_type, types, type_chart)
            for name, types in team.items()
        }

    table = pd.DataFrame.from_dict(rows, orient="index")
    table["# weak"] = (table[list(team)] > 1).sum(axis=1)
    table["# resist"] = (table[list(team)] < 1).sum(axis=1)
    table["total"] = table[list(team)].sum(axis=1)

    return table.sort_values(
        by=["# weak", "# resist", "total"],
        ascending=[False, True, False],
    )

def coverage_gaps(team: dict[str, list[str]], type_chart: dict) -> set[str]:
    """Types the team's own types can't hit super-effectively."""
    team_types = {t for types in team.values() for t in types}
    covered = set()
    for attacking_type in team_types:
        covered |= set(type_chart[attacking_type]["double_damage_to"])
    return set(type_chart) - covered