"""Structured differences between current and proposed type analysis."""

from dataclasses import dataclass

import pandas as pd

from pokedex.team_summary import QuadWeakness, summarize_team
from pokedex.types import Team


@dataclass(frozen=True)
class WeaknessChange:
    attack_type: str
    before_members: tuple[str, ...]
    after_members: tuple[str, ...]


@dataclass(frozen=True)
class SwapExplanation:
    reduced_shared_weaknesses: tuple[WeaknessChange, ...] = ()
    increased_shared_weaknesses: tuple[WeaknessChange, ...] = ()
    removed_quad_weaknesses: tuple[QuadWeakness, ...] = ()
    added_quad_weaknesses: tuple[QuadWeakness, ...] = ()
    closed_native_gaps: tuple[str, ...] = ()
    opened_native_gaps: tuple[str, ...] = ()


def compare_type_analysis(
    *,
    current_team: Team,
    proposed_team: Team,
    current_table: pd.DataFrame,
    proposed_table: pd.DataFrame,
    current_gaps: set[str],
    proposed_gaps: set[str],
) -> SwapExplanation:
    """Compare matching analysis inputs without fetching data or scoring swaps."""
    current_types = set(current_table.index)
    proposed_types = set(proposed_table.index)

    if current_types != proposed_types:
        raise ValueError("Both defensive tables must cover the same attack types.")

    reduced: list[WeaknessChange] = []
    increased: list[WeaknessChange] = []

    for attack_type in sorted(current_types):
        before = tuple(name for name in current_team if current_table.loc[attack_type, name] > 1)
        after = tuple(name for name in proposed_team if proposed_table.loc[attack_type, name] > 1)

        if max(len(before), len(after)) < 2:
            continue

        change = WeaknessChange(attack_type, before, after)

        if len(after) < len(before):
            reduced.append(change)
        elif len(after) > len(before):
            increased.append(change)

    current_summary = summarize_team(
        current_team,
        current_table,
        current_gaps,
    )
    proposed_summary = summarize_team(
        proposed_team,
        proposed_table,
        proposed_gaps,
    )

    current_quad = set(current_summary.quad_weaknesses)
    proposed_quad = set(proposed_summary.quad_weaknesses)

    def ordered_quad(
        weaknesses: set[QuadWeakness],
    ) -> tuple[QuadWeakness, ...]:
        return tuple(
            sorted(
                weaknesses,
                key=lambda weakness: (
                    weakness.species,
                    weakness.attack_type,
                ),
            )
        )

    return SwapExplanation(
        reduced_shared_weaknesses=tuple(reduced),
        increased_shared_weaknesses=tuple(increased),
        removed_quad_weaknesses=ordered_quad(current_quad - proposed_quad),
        added_quad_weaknesses=ordered_quad(proposed_quad - current_quad),
        closed_native_gaps=tuple(sorted(current_gaps - proposed_gaps)),
        opened_native_gaps=tuple(sorted(proposed_gaps - current_gaps)),
    )
