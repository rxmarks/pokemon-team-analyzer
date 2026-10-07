"""Validated, immutable team state independent of Streamlit."""

import re
from dataclasses import dataclass

from pokedex.config import MAX_MOVES, MAX_TEAM_SIZE
from pokedex.showdown import ShowdownMon
from pokedex.types import Team

_IDENTIFIER = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def _validate_identifier(value: str, label: str) -> None:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase hyphenated identifier.")


@dataclass(frozen=True)
class TeamMember:
    """One member's supported build state."""

    species: str
    moves: tuple[str, ...] = ()
    locked: bool = False

    def __post_init__(self) -> None:
        _validate_identifier(self.species, "Species")

        if not isinstance(self.moves, tuple):
            raise ValueError("Moves must be a tuple.")

        if len(self.moves) > MAX_MOVES:
            raise ValueError(f"A member can have at most {MAX_MOVES} moves.")

        for move in self.moves:
            _validate_identifier(move, "Move")

        if len(set(self.moves)) != len(self.moves):
            raise ValueError("A member cannot have duplicate moves.")

        if not isinstance(self.locked, bool):
            raise ValueError("Locked must be a boolean.")


@dataclass(frozen=True)
class TeamState:
    """An ordered team with unique species and independently stored moves."""

    members: tuple[TeamMember, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.members, tuple):
            raise ValueError("Members must be a tuple.")

        if len(self.members) > MAX_TEAM_SIZE:
            raise ValueError(f"A team can have at most {MAX_TEAM_SIZE} members.")

        if any(not isinstance(member, TeamMember) for member in self.members):
            raise ValueError("Every member must be a TeamMember.")

        species = [member.species for member in self.members]
        if len(set(species)) != len(species):
            raise ValueError("A team cannot have duplicate species.")

    @property
    def species(self) -> tuple[str, ...]:
        return tuple(member.species for member in self.members)

    @property
    def locked_members(self) -> frozenset[str]:
        return frozenset(member.species for member in self.members if member.locked)

    def to_analysis_team(self, species_types: Team) -> Team:
        """Return a fresh type mapping in member order without fetching data."""
        team: Team = {}

        for member in self.members:
            if member.species not in species_types:
                raise ValueError(f"Missing types for '{member.species}'.")

            types = species_types[member.species]
            if not types:
                raise ValueError(f"Empty types for '{member.species}'.")

            team[member.species] = list(types)

        return team

    @classmethod
    def from_showdown(cls, parsed: list[ShowdownMon]) -> "TeamState":
        """Convert parsed members without silently deduplicating them."""
        return cls(
            members=tuple(
                TeamMember(species=member.species, moves=tuple(member.moves)) for member in parsed
            )
        )
