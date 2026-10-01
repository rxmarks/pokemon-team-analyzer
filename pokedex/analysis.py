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

def team_badness(team: dict[str, list[str]], type_chart: dict) -> int:
    """Problem types (more weak than resist) + offensive coverage gaps. Lower is better."""
    table = team_table(team, type_chart)
    problem_types = int((table["# weak"] > table["# resist"]).sum())
    return problem_types + len(coverage_gaps(team, type_chart))

def team_weak_total(team: dict[str, list[str]], type_chart: dict) -> int:
    """Total number of (attack type, member) pairs where the member is weak. Tiebreaker."""
    return int(team_table(team, type_chart)["# weak"].sum())

def suggest_swaps(
    team: dict[str, list[str]],
    candidates: dict[str, list[str]],
    type_chart: dict,
    top_n: int = 5,
) -> pd.DataFrame:
    """For each candidate, find the best member to replace and rank by improvement."""
    base = team_badness(team, type_chart)
    results = []

    for cand_name, cand_types in candidates.items():
        if cand_name in team:
            continue
        best = None
        for member in team:
            new_team = {n: t for n, t in team.items() if n != member}
            new_team[cand_name] = cand_types
            score = (team_badness(new_team, type_chart), team_weak_total(new_team, type_chart))
            if best is None or score < (best["new_badness"], best["weak_total"]):
                best = {
                    "candidate": cand_name,
                    "replaces": member,
                    "new_badness": score[0],
                    "weak_total": score[1],
                    "improvement": base - score[0],
                }
        results.append(best)

    ranked = pd.DataFrame(results).sort_values(
        by=["improvement", "weak_total", "candidate"],
        ascending=[False, True, True],
    )
    return ranked.head(top_n).reset_index(drop=True)

FAST_SPEED = 100

def stat_warnings(team_stats: dict[str, dict[str, int]]) -> list[str]:
    """Flag missing team roles based on base stats."""
    stats = list(team_stats.values())
    warnings = []
    if not any(s["speed"] >= FAST_SPEED for s in stats):
        warnings.append(f"No fast Pokémon (nobody has base Speed {FAST_SPEED}+).")
    if not any(s["special-attack"] > s["attack"] for s in stats):
        warnings.append("No special attackers (everyone's Attack is higher than Special Attack).")
    if not any(s["attack"] > s["special-attack"] for s in stats):
        warnings.append("No physical attackers (everyone's Special Attack is higher than Attack).")
    return warnings