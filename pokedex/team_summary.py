"""Structured summary facts from existing type-analysis results."""

from dataclasses import dataclass

import pandas as pd

from pokedex.types import Team


@dataclass(frozen=True)
class SharedWeakness:
    attack_type: str
    members: tuple[str, ...]


@dataclass(frozen=True)
class QuadWeakness:
    species: str
    attack_type: str


@dataclass(frozen=True)
class TeamSummary:
    shared_weaknesses: tuple[SharedWeakness, ...] = ()
    quad_weaknesses: tuple[QuadWeakness, ...] = ()
    native_coverage_gaps: tuple[str, ...] = ()


def summarize_team(
    team: Team,
    defensive_table: pd.DataFrame,
    coverage_gaps: set[str],
) -> TeamSummary:
    """Summarize a matching team/table without fetching data or changing scores."""
    if not team:
        return TeamSummary()

    attack_types = sorted(defensive_table.index)
    shared: list[SharedWeakness] = []
    quad: list[QuadWeakness] = []

    for attack_type in attack_types:
        weak_members = tuple(name for name in team if defensive_table.loc[attack_type, name] > 1)

        if len(weak_members) >= 2:
            shared.append(
                SharedWeakness(
                    attack_type=attack_type,
                    members=weak_members,
                )
            )

    shared.sort(
        key=lambda weakness: (
            -len(weakness.members),
            weakness.attack_type,
        )
    )

    for name in team:
        for attack_type in attack_types:
            if defensive_table.loc[attack_type, name] >= 4:
                quad.append(
                    QuadWeakness(
                        species=name,
                        attack_type=attack_type,
                    )
                )

    return TeamSummary(
        shared_weaknesses=tuple(shared),
        quad_weaknesses=tuple(quad),
        native_coverage_gaps=tuple(sorted(coverage_gaps)),
    )
