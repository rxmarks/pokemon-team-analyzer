import pytest

from pokedex.team_state import TeamMember, TeamState
from pokedex.workspace_files import WorkspaceState
from pokedex.workspace_session import (
    CUSTOM_SOURCE_LABEL,
    DEFAULT_SOURCE_LABEL,
    restore_workspace,
    snapshot_workspace,
)


def saved_workspace():
    return WorkspaceState(
        team=TeamState(
            members=(
                TeamMember(
                    "garchomp",
                    moves=("earthquake",),
                    locked=True,
                ),
                TeamMember("tyranitar", moves=("crunch",)),
            )
        ),
        available_pokemon=("togekiss", "dragonite"),
        candidate_source="custom",
        opponent_team=("ferrothorn", "gyarados"),
        matchup_improvements_only=False,
    )


def test_snapshot_captures_supported_workspace_state():
    state = {
        "team": ["garchomp", "tyranitar"],
        "moves_garchomp": ["earthquake"],
        "moves_tyranitar": ["crunch"],
        "locked_members": ["garchomp"],
        "available_pokemon": ["togekiss", "dragonite"],
        "candidate_source": CUSTOM_SOURCE_LABEL,
        "opponent_team": ["ferrothorn", "gyarados"],
        "matchup_improvements_only": False,
    }

    assert snapshot_workspace(state) == saved_workspace()


def test_snapshot_uses_defaults_for_missing_preferences():
    snapshot = snapshot_workspace({})

    assert snapshot == WorkspaceState()


def test_snapshot_does_not_share_mutable_lists():
    state = {
        "team": ["garchomp"],
        "moves_garchomp": ["earthquake"],
        "available_pokemon": ["dragonite"],
        "opponent_team": ["ferrothorn"],
    }

    snapshot = snapshot_workspace(state)

    state["team"].append("tyranitar")
    state["moves_garchomp"].append("swords-dance")
    state["available_pokemon"].append("togekiss")
    state["opponent_team"].append("gyarados")

    assert snapshot.team.species == ("garchomp",)
    assert snapshot.team.members[0].moves == ("earthquake",)
    assert snapshot.available_pokemon == ("dragonite",)
    assert snapshot.opponent_team == ("ferrothorn",)


def test_snapshot_rejects_unknown_source_label():
    with pytest.raises(ValueError, match="candidate-source"):
        snapshot_workspace({"candidate_source": "Unknown mode"})


def test_restore_replaces_workspace_and_clears_transient_state():
    state = {
        "team": ["dragonite"],
        "moves_dragonite": ["ice-beam"],
        "locked_members": ["dragonite"],
        "available_pokemon": ["gyarados"],
        "candidate_source": DEFAULT_SOURCE_LABEL,
        "opponent_team": ["togekiss"],
        "matchup_improvements_only": True,
        "team_before_swap": TeamState(),
        "last_swap": ("garchomp", "dragonite"),
        "pending_swap": ("dragonite", "togekiss"),
        "import_ok": True,
        "import_skipped": ["missingno"],
        "import_notes": ["Old import"],
        "team_file_error": "Old error",
        "team_file_success": "Old success",
        "pool_import_message": "Old pool import",
        "workspace_file_error": "Old workspace error",
        "workspace_file_success": "Old workspace success",
        "showdown_paste": "Old team paste",
        "pool_paste": "Old pool paste",
        "unrelated_setting": "keep",
    }

    snapshot = saved_workspace()
    restore_workspace(state, snapshot)

    assert snapshot_workspace(state) == snapshot
    assert state["team_state"] == snapshot.team
    assert state["team"] == ["garchomp", "tyranitar"]
    assert state["moves_garchomp"] == ["earthquake"]
    assert state["moves_tyranitar"] == ["crunch"]
    assert "moves_dragonite" not in state
    assert state["candidate_source"] == CUSTOM_SOURCE_LABEL
    assert state["showdown_paste"] == ""
    assert state["pool_paste"] == ""
    assert state["unrelated_setting"] == "keep"

    for key in (
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
    ):
        assert key not in state


def test_restore_lists_are_independent_of_snapshot():
    snapshot = saved_workspace()
    state = {}

    restore_workspace(state, snapshot)

    state["team"].append("ferrothorn")
    state["moves_garchomp"].append("swords-dance")
    state["locked_members"].clear()
    state["available_pokemon"].append("gyarados")
    state["opponent_team"].clear()

    assert snapshot == saved_workspace()


def test_restore_empty_workspace_clears_previous_selections():
    state = {
        "team": ["garchomp"],
        "moves_garchomp": ["earthquake"],
        "locked_members": ["garchomp"],
        "available_pokemon": ["dragonite"],
        "candidate_source": CUSTOM_SOURCE_LABEL,
        "opponent_team": ["ferrothorn"],
        "matchup_improvements_only": False,
    }

    restore_workspace(state, WorkspaceState())

    assert snapshot_workspace(state) == WorkspaceState()
    assert state["team"] == []
    assert state["available_pokemon"] == []
    assert state["opponent_team"] == []
    assert state["locked_members"] == []
    assert state["candidate_source"] == DEFAULT_SOURCE_LABEL
    assert state["matchup_improvements_only"] is True
    assert "moves_garchomp" not in state
