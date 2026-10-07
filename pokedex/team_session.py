"""Bridge widget state and immutable team snapshots."""

from collections.abc import MutableMapping
from typing import Any

from pokedex.team_state import TeamMember, TeamState


def snapshot_team(state: MutableMapping[str, Any]) -> TeamState:
    """Capture current species, selected moves, and locks."""
    locks = set(state.get("locked_members", []))

    return TeamState(
        members=tuple(
            TeamMember(
                species=name,
                moves=tuple(state.get(f"moves_{name}", [])),
                locked=name in locks,
            )
            for name in state.get("team", [])
        )
    )


def restore_team(
    state: MutableMapping[str, Any],
    snapshot: TeamState,
) -> None:
    """Restore a snapshot and remove move state belonging to other members."""
    for key in list(state):
        if key.startswith("moves_"):
            state.pop(key, None)

    state["team"] = list(snapshot.species)
    state["locked_members"] = [member.species for member in snapshot.members if member.locked]

    for member in snapshot.members:
        state[f"moves_{member.species}"] = list(member.moves)

    state["team_state"] = snapshot


def reconcile_team(state: MutableMapping[str, Any]) -> TeamState:
    """Remove stale member state while preserving retained members' builds."""
    current_team = set(state.get("team", []))

    state["locked_members"] = [
        name for name in state.get("locked_members", []) if name in current_team
    ]

    for key in list(state):
        if key.startswith("moves_") and key.removeprefix("moves_") not in current_team:
            state.pop(key, None)

    snapshot = snapshot_team(state)
    state["team_state"] = snapshot
    return snapshot
