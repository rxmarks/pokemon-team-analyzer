from typing import Any, TypedDict

import pandas as pd

from pokedex.config import FAST_SPEED, TOP_N_SWAPS
from pokedex.types import MoveCache, Team, TypeChart

SWAP_COLUMNS = ["candidate", "replaces", "new_badness", "weak_total", "improvement"]

MATCHUP_SWAP_COLUMNS = [
    "candidate",
    "replaces",
    "threat_pressure",
    "matchup_balance",
    "new_badness",
    "weak_total",
    "pressure_improvement",
]

OPPONENT_THREAT_COLUMNS = [
    "opponent",
    "threatens",
    "answered_by",
    "threat_score",
    "weak_members",
    "answers",
]


class MatchupSwap(TypedDict):
    candidate: str
    replaces: str
    threat_pressure: int
    matchup_balance: float
    new_badness: int
    weak_total: int
    pressure_improvement: int


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
    """Types the team's own types cannot hit super-effectively."""
    team_types = {type_name for types in team.values() for type_name in types}
    return gaps_from_attack_types(team_types, type_chart)


def team_badness(team: Team, type_chart: TypeChart) -> int:
    """Problem types (more weak than resist) + coverage gaps. Lower is better."""
    table = team_table(team, type_chart)
    problem_types = int((table["# weak"] > table["# resist"]).sum())

    return problem_types + len(coverage_gaps(team, type_chart))


def team_weak_total(team: Team, type_chart: TypeChart) -> int:
    """Total weak attack/member pairs. Used as a lower-is-better tiebreaker."""
    return int(team_table(team, type_chart)["# weak"].sum())


def member_profile(types: list[str], type_chart: TypeChart) -> dict[str, float]:
    """One Pokémon's defensive multiplier against every attack type."""
    return {attack_type: multiplier(attack_type, types, type_chart) for attack_type in type_chart}


def member_coverage(types: list[str], type_chart: TypeChart) -> set[str]:
    """Types this Pokémon's native types hit super-effectively."""
    covered: set[str] = set()

    for type_name in types:
        covered |= set(type_chart[type_name]["double_damage_to"])

    return covered


def score_team(
    profiles: list[dict[str, float]],
    coverages: list[set[str]],
    all_types: list[str],
) -> tuple[int, int]:
    """Return (badness, weak_total) from precomputed profiles and coverage."""
    problems = 0
    weak_total = 0

    for attack_type in all_types:
        weak = sum(1 for profile in profiles if profile[attack_type] > 1)
        resist = sum(1 for profile in profiles if profile[attack_type] < 1)

        weak_total += weak

        if weak > resist:
            problems += 1

    covered = set().union(*coverages)
    gaps = len(set(all_types) - covered)

    return problems + gaps, weak_total


def suggest_swaps(
    team: Team,
    candidates: Team,
    type_chart: TypeChart,
    top_n: int = TOP_N_SWAPS,
) -> pd.DataFrame:
    """For each candidate, find the generic best member to replace."""
    all_types = list(type_chart)
    profiles = {name: member_profile(types, type_chart) for name, types in team.items()}
    coverages = {name: member_coverage(types, type_chart) for name, types in team.items()}
    base_badness, _ = score_team(
        list(profiles.values()),
        list(coverages.values()),
        all_types,
    )

    results: list[dict[str, Any]] = []

    for candidate_name, candidate_types in candidates.items():
        if candidate_name in team:
            continue

        candidate_profile = member_profile(candidate_types, type_chart)
        candidate_coverage = member_coverage(candidate_types, type_chart)
        best: dict[str, Any] | None = None

        for replaced_name in team:
            remaining_names = [member_name for member_name in team if member_name != replaced_name]
            score = score_team(
                [profiles[name] for name in remaining_names] + [candidate_profile],
                [coverages[name] for name in remaining_names] + [candidate_coverage],
                all_types,
            )

            if best is None or score < (
                best["new_badness"],
                best["weak_total"],
            ):
                best = {
                    "candidate": candidate_name,
                    "replaces": replaced_name,
                    "new_badness": score[0],
                    "weak_total": score[1],
                    "improvement": base_badness - score[0],
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

    if not any(stat["speed"] >= FAST_SPEED for stat in stats):
        warnings.append(f"No fast Pokémon (nobody has base Speed {FAST_SPEED}+).")

    if not any(stat["special-attack"] > stat["attack"] for stat in stats):
        warnings.append("No special attackers (everyone's Attack is higher than Special Attack).")

    if not any(stat["attack"] > stat["special-attack"] for stat in stats):
        warnings.append("No physical attackers (everyone's Special Attack is higher than Attack).")

    return warnings


def damaging_move_types(moves: list[str], move_cache: MoveCache) -> set[str]:
    """Return types of damaging known moves; skip status and unknown moves."""
    move_types: set[str] = set()

    for name in moves:
        info = move_cache.get(name)

        if info is None or info["damage_class"] == "status":
            continue

        move_types.add(info["type"])

    return move_types


def move_coverage_gaps(
    team_moves: dict[str, list[str]],
    move_cache: MoveCache,
    type_chart: TypeChart,
) -> set[str]:
    """Types the team's damaging moves cannot hit super-effectively."""
    attack_types: set[str] = set()

    for moves in team_moves.values():
        attack_types |= damaging_move_types(moves, move_cache)

    return gaps_from_attack_types(attack_types, type_chart)


def best_stab_multiplier(
    attacker_types: list[str],
    defender_types: list[str],
    type_chart: TypeChart,
) -> float:
    """Return the strongest native-type multiplier against the defender."""
    return max(
        multiplier(attack_type, defender_types, type_chart) for attack_type in attacker_types
    )


def matchup_score(
    own_types: list[str],
    opponent_types: list[str],
    type_chart: TypeChart,
) -> float:
    """Positive is favorable for own_types; negative is risky."""
    own_offense = best_stab_multiplier(own_types, opponent_types, type_chart)
    opponent_offense = best_stab_multiplier(
        opponent_types,
        own_types,
        type_chart,
    )

    return own_offense - opponent_offense


def matchup_label(score: float) -> str:
    """Return a readable favorable/even/risky matchup category."""
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
    """Rows are user-team members; columns are opponents; values are labels."""
    table = pd.DataFrame(index=list(team))

    for opponent_name, opponent_types in opponent_team.items():
        table[opponent_name] = [
            matchup_label(matchup_score(own_types, opponent_types, type_chart))
            for own_types in team.values()
        ]

    return table


def threat_report(
    team: Team,
    threats: Team,
    type_chart: TypeChart,
) -> list[dict[str, Any]]:
    """Summarize weaknesses and answers for each predefined meta threat."""
    report: list[dict[str, Any]] = []

    for threat_name, threat_types in threats.items():
        weak = sum(
            1
            for member_types in team.values()
            if best_stab_multiplier(threat_types, member_types, type_chart) > 1
        )
        answers = sum(
            1
            for member_types in team.values()
            if best_stab_multiplier(member_types, threat_types, type_chart) > 1
        )

        report.append(
            {
                "threat": threat_name,
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
    """Return a detailed threat report for a chosen opponent team."""
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

    if not rows:
        return pd.DataFrame(columns=OPPONENT_THREAT_COLUMNS)

    return (
        pd.DataFrame(rows, columns=OPPONENT_THREAT_COLUMNS)
        .sort_values(
            by=["threat_score", "threatens", "opponent"],
            ascending=[False, False, True],
        )
        .reset_index(drop=True)
    )


def matchup_threat_pressure(
    team: Team,
    opponent_team: Team,
    type_chart: TypeChart,
) -> int:
    """Sum opponent threat scores. Lower is better."""
    report = opponent_threat_report(team, opponent_team, type_chart)

    if report.empty:
        return 0

    return int(report["threat_score"].sum())


def team_matchup_balance(
    team: Team,
    opponent_team: Team,
    type_chart: TypeChart,
) -> float:
    """Sum type-pressure scores across every team-member/opponent pairing."""
    return sum(
        matchup_score(member_types, opponent_types, type_chart)
        for member_types in team.values()
        for opponent_types in opponent_team.values()
    )


def matchup_swap_rank(row: MatchupSwap) -> tuple[int, float, int, int, str]:
    """Return a lower-is-better sort key for one matchup-specific swap."""
    return (
        row["threat_pressure"],
        -row["matchup_balance"],
        row["new_badness"],
        row["weak_total"],
        row["replaces"],
    )


def suggest_matchup_swaps(
    team: Team,
    candidates: Team,
    opponent_team: Team,
    type_chart: TypeChart,
    top_n: int = TOP_N_SWAPS,
) -> pd.DataFrame:
    """Rank swaps using precomputed type profiles and opponent contributions."""
    if not team or not opponent_team or top_n <= 0:
        return pd.DataFrame(columns=MATCHUP_SWAP_COLUMNS)

    all_types = list(type_chart)
    member_names = list(team)
    profiles = {name: member_profile(types, type_chart) for name, types in team.items()}
    coverages = {name: member_coverage(types, type_chart) for name, types in team.items()}

    def opponent_contribution(types: list[str]) -> tuple[int, float]:
        pressure = 0
        balance = 0.0

        for opponent_types in opponent_team.values():
            own_offense = best_stab_multiplier(types, opponent_types, type_chart)
            enemy_offense = best_stab_multiplier(opponent_types, types, type_chart)

            pressure += int(enemy_offense > 1) - int(own_offense > 1)
            balance += own_offense - enemy_offense

        return pressure, balance

    contributions = {name: opponent_contribution(types) for name, types in team.items()}
    base_pressure = sum(value[0] for value in contributions.values())
    base_balance = sum(value[1] for value in contributions.values())

    remaining_profiles = {
        name: [profiles[other] for other in member_names if other != name] for name in member_names
    }
    remaining_coverages = {
        name: [coverages[other] for other in member_names if other != name] for name in member_names
    }

    results: list[MatchupSwap] = []

    for candidate_name, candidate_types in candidates.items():
        if candidate_name in team:
            continue

        candidate_profile = member_profile(candidate_types, type_chart)
        candidate_coverage = member_coverage(candidate_types, type_chart)
        candidate_pressure, candidate_balance = opponent_contribution(candidate_types)

        best: MatchupSwap | None = None

        for replaced_name in member_names:
            removed_pressure, removed_balance = contributions[replaced_name]
            pressure = base_pressure - removed_pressure + candidate_pressure
            balance = base_balance - removed_balance + candidate_balance

            new_badness, weak_total = score_team(
                remaining_profiles[replaced_name] + [candidate_profile],
                remaining_coverages[replaced_name] + [candidate_coverage],
                all_types,
            )

            result: MatchupSwap = {
                "candidate": candidate_name,
                "replaces": replaced_name,
                "threat_pressure": pressure,
                "matchup_balance": balance,
                "new_badness": new_badness,
                "weak_total": weak_total,
                "pressure_improvement": base_pressure - pressure,
            }

            if best is None or matchup_swap_rank(result) < matchup_swap_rank(best):
                best = result

        if best is not None:
            results.append(best)

    if not results:
        return pd.DataFrame(columns=MATCHUP_SWAP_COLUMNS)

    return (
        pd.DataFrame(results, columns=MATCHUP_SWAP_COLUMNS)
        .sort_values(
            by=[
                "threat_pressure",
                "matchup_balance",
                "new_badness",
                "weak_total",
                "candidate",
                "replaces",
            ],
            ascending=[True, False, True, True, True, True],
        )
        .head(top_n)
        .reset_index(drop=True)
    )
