"""Eligibility checks for analysis-dependent actions."""

from collections.abc import Collection


def has_complete_team(
    selected_species: Collection[str],
    loaded_species: Collection[str],
) -> bool:
    """Require a nonempty selection and exactly its species to be loaded."""
    return bool(selected_species) and set(selected_species) == set(loaded_species)
