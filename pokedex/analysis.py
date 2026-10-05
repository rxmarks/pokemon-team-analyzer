from typing import Any

import pandas as pd

from pokedex.config import FAST_SPEED, TOP_N_SWAPS
from pokedex.types import MoveCache, Team, TypeChart

SWAP_COLUMNS = ["candidate", "replaces", "new_badness", "weak_total", "improvement"]


def multiplier(attack_type: str, defender_types: list[str], type_chart: TypeChart) -> float:
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


def team_table(team: Team, type_chart: TypeChart) -> pd.DataFrame:
    """Rows = attack types, columns = team members, plus weak/resist counts."""
    rows: dict[str, dict[str, float]] = {}
    for attack_type in type_chart:
        rows[attack_type] = {
            name: multiplier(attack_type, types, type_chart) for name, types in team.items()
        }

    table = pd.DataFrame.from_dict(rows, orient="index")
    table["# weak"] = (table[list(team)] > 1).sum(axis=1)
    table["# resist"] = (table[list(team)] < 1).sum(axis=1)
    table["total"] = table[list(team)].sum(axis=1)

    return table.sort_values(
        by=["# weak", "# resist", "total"],
        ascending=[False, True, False],
    )


def gaps_from_attack_types(attack_types: set[str], type_chart: TypeChart) -> set[str]:
    """Types that none of the given attack types hit super-effectively."""
    covered: set[str] = set()
    for attacking_type in attack_types:
        covered |= set(type_chart[attacking_type]["double_damage_to"])
    return set(type_chart) - covered


def coverage_gaps(team: Team, type_chart: TypeChart) -> set[str]:
    """Types the team's own types can't hit super-effectively."""
    team_types = {t for types in team.values() for t in types}
    return gaps_from_attack_types(team_types, type_chart)


def team_badness(team: Team, type_chart: TypeChart) -> int:
    """Problem types (more weak than resist) + offensive coverage gaps. Lower is better."""
    table = team_table(team, type_chart)
    problem_types = int((table["# weak"] > table["# resist"]).sum())
    return problem_types + len(coverage_gaps(team, type_chart))


def team_weak_total(team: Team, type_chart: TypeChart) -> int:
    """Total number of (attack type, member) pairs where the member is weak. Tiebreaker."""
    return int(team_table(team, type_chart)["# weak"].sum())


def member_profile(types: list[str], type_chart: TypeChart) -> dict[str, float]:
    """One Pokémon's multiplier against each of the 18 attack types."""
    return {attack: multiplier(attack, types, type_chart) for attack in type_chart}


def member_coverage(types: list[str], type_chart: TypeChart) -> set[str]:
    """Types this Pokémon's own types hit super-effectively."""
    covered: set[str] = set()
    for t in types:
        covered |= set(type_chart[t]["double_damage_to"])
    return covered


def score_team(
    profiles: list[dict[str, float]],
    coverages: list[set[str]],
    all_types: list[str],
) -> tuple[int, int]:
    """(badness, weak_total) using precomputed profiles. Same math as team_badness, no pandas."""
    problems = 0
    weak_total = 0
    for attack in all_types:
        weak = sum(1 for p in profiles if p[attack] > 1)
        resist = sum(1 for p in profiles if p[attack] < 1)
        weak_total += weak
        if weak > resist:
            problems += 1
    covered: set[str] = set()
    covered = covered.union(*coverages)
    gaps = len(set(all_types) - covered)
    return problems + gaps, weak_total


def suggest_swaps(
    team: Team,
    candidates: Team,
    type_chart: TypeChart,
    top_n: int = TOP_N_SWAPS,
    opponent_team: Team | None = None,
) -> pd.DataFrame:
    """For each candidate, find the best member to replace and rank by improvement."""
    all_types = list(type_chart)
    profiles = {n: member_profile(t, type_chart) for n, t in team.items()}
    coverages = {n: member_coverage(t, type_chart) for n, t in team.items()}
    base, _ = score_team(list(profiles.values()), list(coverages.values()), all_types)

    results: list[dict[str, Any]] = []
    for cand_name, cand_types in candidates.items():
        if cand_name in team:
            continue
        cand_profile = member_profile(cand_types, type_chart)
        cand_cov = member_coverage(cand_types, type_chart)
        best: dict[str, Any] | None = None
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
        if best is not None:
            results.append(best)

    if not results:
        return pd.DataFrame(columns=SWAP_COLUMNS)

    ranked = pd.DataFrame(results, columns=SWAP_COLUMNS).sort_values(
        by=["improvement", "weak_total", "candidate"],
        ascending=[False, True, True],
    )
    return ranked.head(top_n).reset_index(drop=True)


def stat_warnings(team_stats: dict[str, dict[str, int]]) -> list[str]:
    """Flag missing team roles based on base stats."""
    stats = list(team_stats.values())
    warnings: list[str] = []
    if not any(s["speed"] >= FAST_SPEED for s in stats):
        warnings.append(f"No fast Pokémon (nobody has base Speed {FAST_SPEED}+).")
    if not any(s["special-attack"] > s["attack"] for s in stats):
        warnings.append("No special attackers (everyone's Attack is higher than Special Attack).")
    if not any(s["attack"] > s["special-attack"] for s in stats):
        warnings.append("No physical attackers (everyone's Special Attack is higher than Attack).")
    return warnings


def damaging_move_types(moves: list[str], move_cache: MoveCache) -> set[str]:
    """Types of the damaging moves in the list; status and unknown moves are skipped."""
    types: set[str] = set()
    for name in moves:
        info = move_cache.get(name)
        if info is None or info["damage_class"] == "status":
            continue
        types.add(info["type"])
    return types


def move_coverage_gaps(
    team_moves: dict[str, list[str]],
    move_cache: MoveCache,
    type_chart: TypeChart,
) -> set[str]:
    """Types the team's damaging moves can't hit super-effectively."""
    attack_types: set[str] = set()
    for moves in team_moves.values():
        attack_types |= damaging_move_types(moves, move_cache)
    return gaps_from_attack_types(attack_types, type_chart)


def best_stab_multiplier(
    attacker_types: list[str],
    defender_types: list[str],
    type_chart: TypeChart,
) -> float:
    """Best damage multiplier from an attacker's native types."""
    return max(
        multiplier(attack_type, defender_types, type_chart) for attack_type in attacker_types
    )


def matchup_score(
    own_types: list[str],
    opponent_types: list[str],
    type_chart: TypeChart,
) -> float:
    """Type-pressure score: positive is favorable for own_types, negative is risky."""
    return best_stab_multiplier(own_types, opponent_types, type_chart) - best_stab_multiplier(
        opponent_types, own_types, type_chart
    )


def matchup_label(score: float) -> str:
    """Human-readable label for a type-pressure score."""
    if score > 0:
        return "Favorable"
    if score < 0:
        return "Risky"
    return "Even"


def matchup_table(
    team: Team,
    opponent_team: Team,
    type_chart: TypeChart,
) -> pd.DataFrame:
    """Rows are user-team members, columns are opponents, values are matchup labels."""
    return pd.DataFrame(
        {
            opponent_name: {
                own_name: matchup_label(matchup_score(own_types, opponent_types, type_chart))
                for own_name, own_types in team.items()
            }
            for opponent_name, opponent_types in opponent_team.items()
        }
    )


def threat_report(
    team: Team,
    threats: Team,
    type_chart: TypeChart,
) -> list[dict[str, Any]]:
    """Per threat: members weak to its types, and members that hit it super-effectively."""
    report: list[dict[str, Any]] = []
    for threat, threat_types in threats.items():
        weak = sum(
            1
            for member_types in team.values()
            if max(multiplier(t, member_types, type_chart) for t in threat_types) > 1
        )
        answers = sum(
            1
            for member_types in team.values()
            if max(multiplier(t, threat_types, type_chart) for t in member_types) > 1
        )
        report.append(
            {
                "threat": threat,
                "members_weak": weak,
                "answers": answers,
                "danger": answers == 0 or weak >= 3,
            }
        )
    return report


def opponent_threat_report(
    team: Team,
    opponent_team: Team,
    type_chart: TypeChart,
) -> pd.DataFrame:
    """Detailed type-based threat report for a user-entered opponent team."""
    rows: list[dict[str, Any]] = []

    for opponent_name, opponent_types in opponent_team.items():
        weak_members = [
            member_name
            for member_name, member_types in team.items()
            if best_stab_multiplier(opponent_types, member_types, type_chart) > 1
        ]
        answers = [
            member_name
            for member_name, member_types in team.items()
            if best_stab_multiplier(member_types, opponent_types, type_chart) > 1
        ]
        rows.append(
            {
                "opponent": opponent_name,
                "threatens": len(weak_members),
                "answered_by": len(answers),
                "threat_score": len(weak_members) - len(answers),
                "weak_members": ", ".join(weak_members) or "None",
                "answers": ", ".join(answers) or "None",
            }
        )

    return (
        pd.DataFrame(rows)
        .sort_values(
            ["threat_score", "threatens", "opponent"],
            ascending=[False, False, True],
        )
        .reset_index(drop=True)
    )
