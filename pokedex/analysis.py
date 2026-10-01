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

def member_profile(types: list[str], type_chart: dict) -> dict[str, float]:
    """One Pokémon's multiplier against each of the 18 attack types."""
    return {attack: multiplier(attack, types, type_chart) for attack in type_chart}


def member_coverage(types: list[str], type_chart: dict) -> set[str]:
    """Types this Pokémon's own types hit super-effectively."""
    covered = set()
    for t in types:
        covered |= set(type_chart[t]["double_damage_to"])
    return covered


def score_team(profiles: list[dict], coverages: list[set], all_types: list[str]) -> tuple[int, int]:
    """(badness, weak_total) using precomputed profiles. Same math as team_badness, no pandas."""
    problems = 0
    weak_total = 0
    for attack in all_types:
        weak = sum(1 for p in profiles if p[attack] > 1)
        resist = sum(1 for p in profiles if p[attack] < 1)
        weak_total += weak
        if weak > resist:
            problems += 1
    gaps = len(set(all_types) - set().union(*coverages))
    return problems + gaps, weak_total

def suggest_swaps(
    team: dict[str, list[str]],
    candidates: dict[str, list[str]],
    type_chart: dict,
    top_n: int = 5,
) -> pd.DataFrame:
    """For each candidate, find the best member to replace and rank by improvement."""
    all_types = list(type_chart)
    profiles = {n: member_profile(t, type_chart) for n, t in team.items()}
    coverages = {n: member_coverage(t, type_chart) for n, t in team.items()}
    base, _ = score_team(list(profiles.values()), list(coverages.values()), all_types)

    results = []
    for cand_name, cand_types in candidates.items():
        if cand_name in team:
            continue
        cand_profile = member_profile(cand_types, type_chart)
        cand_cov = member_coverage(cand_types, type_chart)
        best = None
        for member in team:
            others = [m for m in team if m != member]
            score = score_team(
                [profiles[m] for m in others] + [cand_profile],
                [coverages[m] for m in others] + [cand_cov],
                all_types,
            )
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

