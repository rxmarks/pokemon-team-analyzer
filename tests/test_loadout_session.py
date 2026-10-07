from copy import deepcopy

import pytest

from pokedex.config import MAX_MOVES
from pokedex.loadout_session import (
    MoveProposal,
    apply_loadout,
    cancel_loadout,
    loadout_is_current,
    stage_loadout,
)
from pokedex.team_session import reconcile_team, snapshot_team
from pokedex.team_state import TeamMember, TeamState


def sample_state():
    state = {
        "team": ["garchomp", "tyranitar"],
        "moves_garchomp": ["earthquake"],
        "moves_tyranitar": ["crunch"],
        "locked_members": ["garchomp"],
        "available_pokemon": ["dragonite", "togekiss"],
        "candidate_source": "My available Pokémon",
        "opponent_team": ["ferrothorn"],
        "matchup_improvements_only": False,
    }
    reconcile_team(state)
    return state


def test_stage_preserves_build_and_other_state():
    state = sample_state()
    before = deepcopy(state)

    proposal = stage_loadout(
        state,
        "garchomp",
        ["earthquake", "dragon-claw"],
    )

    assert proposal == MoveProposal(
        species="garchomp",
        previous_moves=("earthquake",),
        proposed_moves=("earthquake", "dragon-claw"),
    )
    assert state["pending_loadout"] == proposal
    assert {key: value for key, value in state.items() if key != "pending_loadout"} == before


def test_proposal_does_not_share_input_lists():
    state = sample_state()
    suggested = ["earthquake", "dragon-claw"]

    proposal = stage_loadout(state, "garchomp", suggested)

    suggested.append("fire-fang")
    state["moves_garchomp"].append("swords-dance")

    assert proposal.previous_moves == ("earthquake",)
    assert proposal.proposed_moves == ("earthquake", "dragon-claw")


def test_apply_changes_only_target_moves_and_refreshes_snapshot():
    state = sample_state()
    before = deepcopy(state)

    stage_loadout(state, "garchomp", ["dragon-claw", "fire-fang"])

    assert apply_loadout(state) is True
    assert state["moves_garchomp"] == ["dragon-claw", "fire-fang"]
    assert state["moves_tyranitar"] == ["crunch"]
    assert state["team_state"] == snapshot_team(state)
    assert state["team_state"].members[0].moves == ("dragon-claw", "fire-fang")
    assert "pending_loadout" not in state

    for key in (
        "team",
        "locked_members",
        "available_pokemon",
        "candidate_source",
        "opponent_team",
        "matchup_improvements_only",
    ):
        assert state[key] == before[key]


def test_apply_clears_swap_preview_but_preserves_undo():
    state = sample_state()
    previous = TeamState(members=(TeamMember("dragonite"),))
    state["team_before_swap"] = previous
    state["last_swap"] = ("dragonite", "garchomp")
    state["pending_swap"] = ("tyranitar", "togekiss")

    stage_loadout(state, "garchomp", ["dragon-claw"])

    assert apply_loadout(state) is True
    assert "pending_swap" not in state
    assert state["team_before_swap"] == previous
    assert state["last_swap"] == ("dragonite", "garchomp")


def test_cancel_preserves_build_and_swap_preview():
    state = sample_state()
    state["pending_swap"] = ("tyranitar", "togekiss")
    before = deepcopy(state)

    stage_loadout(state, "garchomp", ["dragon-claw"])
    cancel_loadout(state)

    assert state == before


def test_removed_member_invalidates_proposal():
    state = sample_state()
    proposal = stage_loadout(state, "garchomp", ["dragon-claw"])

    state["team"] = ["tyranitar"]
    reconcile_team(state)
    before = deepcopy(state)

    assert loadout_is_current(state, proposal) is False
    assert apply_loadout(state) is False
    assert "moves_garchomp" not in state
    assert {key: value for key, value in state.items() if key != "pending_loadout"} == {
        key: value for key, value in before.items() if key != "pending_loadout"
    }


def test_changed_moves_invalidate_proposal_without_overwriting_edit():
    state = sample_state()
    proposal = stage_loadout(state, "garchomp", ["dragon-claw"])

    state["moves_garchomp"] = ["swords-dance"]
    reconcile_team(state)

    assert loadout_is_current(state, proposal) is False
    assert apply_loadout(state) is False
    assert state["moves_garchomp"] == ["swords-dance"]
    assert "pending_loadout" not in state


def test_stage_rejects_member_outside_team():
    state = sample_state()
    before = deepcopy(state)

    with pytest.raises(ValueError, match="outside the team"):
        stage_loadout(state, "dragonite", ["dragon-claw"])

    assert state == before


@pytest.mark.parametrize(
    "moves",
    [
        pytest.param([], id="empty"),
        pytest.param(["Ice Beam"], id="invalid-identifier"),
        pytest.param(["earthquake", "earthquake"], id="duplicates"),
        pytest.param(
            [f"move-{index}" for index in range(MAX_MOVES + 1)],
            id="too-many",
        ),
    ],
)
def test_invalid_proposal_does_not_replace_existing_preview(moves):
    state = sample_state()
    original = stage_loadout(state, "garchomp", ["dragon-claw"])
    before = deepcopy(state)

    with pytest.raises(ValueError):
        stage_loadout(state, "garchomp", moves)

    assert state == before
    assert state["pending_loadout"] == original


@pytest.mark.parametrize(
    "pending",
    [
        pytest.param(None, id="none"),
        pytest.param("invalid", id="wrong-type"),
    ],
)
def test_apply_without_valid_proposal_does_not_change_build(pending):
    state = sample_state()
    before = deepcopy(state)
    state["pending_loadout"] = pending

    assert apply_loadout(state) is False
    assert state == before


def test_cancel_without_proposal_is_safe():
    state = sample_state()
    before = deepcopy(state)

    cancel_loadout(state)

    assert state == before
