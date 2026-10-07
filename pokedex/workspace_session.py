"""Bridge application session state and immutable workspace snapshots."""

from collections.abc import MutableMapping
from typing import Any

from pokedex.team_session import restore_team, snapshot_team
from pokedex.workspace_files import WorkspaceState

DEFAULT_SOURCE_LABEL = "Current recommendation pool"
CUSTOM_SOURCE_LABEL = "My available Pokémon"

_TRANSIENT_KEYS = (
    "team_before_swap",
    "last_swap",
    "pending_swap",
    "import_ok",
    "import_skipped",
    "import_notes",
    "team_file_error",
    "team_file_success",
    "pool_import_message",
    "workspace_file_error",
    "workspace_file_success",
)

_PASTE_KEYS = (
    "showdown_paste",
    "pool_paste",
)


def snapshot_workspace(state: MutableMapping[str, Any]) -> WorkspaceState:
    """Capture supported team state and analysis preferences."""
    source_label = state.get("candidate_source", DEFAULT_SOURCE_LABEL)

    if source_label == DEFAULT_SOURCE_LABEL:
        source = "default"
    elif source_label == CUSTOM_SOURCE_LABEL:
        source = "custom"
    else:
        raise ValueError("Unrecognized candidate-source selection.")

    return WorkspaceState(
        team=snapshot_team(state),
        available_pokemon=tuple(state.get("available_pokemon", [])),
        candidate_source=source,
        opponent_team=tuple(state.get("opponent_team", [])),
        matchup_improvements_only=state.get(
            "matchup_improvements_only",
            True,
        ),
    )


def restore_workspace(
    state: MutableMapping[str, Any],
    snapshot: WorkspaceState,
) -> None:
    """Restore a validated workspace and clear superseded transient state."""
    restore_team(state, snapshot.team)

    state["available_pokemon"] = list(snapshot.available_pokemon)
    state["candidate_source"] = (
        CUSTOM_SOURCE_LABEL if snapshot.candidate_source == "custom" else DEFAULT_SOURCE_LABEL
    )
    state["opponent_team"] = list(snapshot.opponent_team)
    state["matchup_improvements_only"] = snapshot.matchup_improvements_only

    for key in _TRANSIENT_KEYS:
        state.pop(key, None)

    for key in _PASTE_KEYS:
        state[key] = ""
