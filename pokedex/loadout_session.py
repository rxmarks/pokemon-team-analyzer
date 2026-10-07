"""Preview and apply suggested moves without replacing the team."""

from collections.abc import MutableMapping
from dataclasses import dataclass
from typing import Any

from pokedex.team_session import reconcile_team
from pokedex.team_state import TeamMember


@dataclass(frozen=True)
class MoveProposal:
    """A proposed move replacement tied to the member's current selections."""

    species: str
    previous_moves: tuple[str, ...]
    proposed_moves: tuple[str, ...]

    def __post_init__(self) -> None:
        TeamMember(
            species=self.species,
            moves=self.previous_moves,
        )
        TeamMember(
            species=self.species,
            moves=self.proposed_moves,
        )

        if not self.proposed_moves:
            raise ValueError("A suggested loadout cannot be empty.")


def stage_loadout(
    state: MutableMapping[str, Any],
    species: str,
    moves: list[str],
) -> MoveProposal:
    """Stage a validated proposal without changing selected moves."""
    if species not in state.get("team", []):
        raise ValueError("Cannot suggest moves for a Pokémon outside the team.")

    proposal = MoveProposal(
        species=species,
        previous_moves=tuple(state.get(f"moves_{species}", [])),
        proposed_moves=tuple(moves),
    )

    state["pending_loadout"] = proposal
    return proposal


def loadout_is_current(
    state: MutableMapping[str, Any],
    proposal: MoveProposal,
) -> bool:
    """Reject proposals whose member is absent or whose selections changed."""
    return (
        proposal.species in state.get("team", [])
        and tuple(state.get(f"moves_{proposal.species}", [])) == proposal.previous_moves
    )


def cancel_loadout(state: MutableMapping[str, Any]) -> None:
    """Dismiss a move proposal without changing the build."""
    state.pop("pending_loadout", None)


def apply_loadout(state: MutableMapping[str, Any]) -> bool:
    """Apply a current proposal to one member; return whether it was applied."""
    proposal = state.get("pending_loadout")

    if not isinstance(proposal, MoveProposal):
        state.pop("pending_loadout", None)
        return False

    if not loadout_is_current(state, proposal):
        state.pop("pending_loadout", None)
        return False

    state[f"moves_{proposal.species}"] = list(proposal.proposed_moves)
    state.pop("pending_loadout", None)
    state.pop("pending_swap", None)
    state.pop("pending_swap_opponents", None)
    reconcile_team(state)

    return True
