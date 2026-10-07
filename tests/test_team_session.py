from pokedex.team_session import reconcile_team, restore_team, snapshot_team
from pokedex.team_state import TeamMember, TeamState


def test_snapshot_captures_moves_locks_and_order():
    state = {
        "team": ["garchomp", "tyranitar"],
        "locked_members": ["tyranitar"],
        "moves_garchomp": ["earthquake"],
        "moves_tyranitar": ["crunch"],
    }

    snapshot = snapshot_team(state)

    assert snapshot.species == ("garchomp", "tyranitar")
    assert snapshot.members[0].moves == ("earthquake",)
    assert snapshot.members[1].moves == ("crunch",)
    assert snapshot.locked_members == frozenset({"tyranitar"})


def test_snapshot_does_not_share_move_lists():
    moves = ["earthquake"]
    state = {"team": ["garchomp"], "moves_garchomp": moves}

    snapshot = snapshot_team(state)
    moves.append("dragon-claw")

    assert snapshot.members[0].moves == ("earthquake",)


def test_restore_removes_stale_moves_and_preserves_unrelated_state():
    state = {
        "team": ["dragonite"],
        "moves_dragonite": ["ice-beam"],
        "opponent_team": ["ferrothorn"],
    }
    snapshot = TeamState(members=(TeamMember("garchomp", moves=("earthquake",), locked=True),))

    restore_team(state, snapshot)

    assert state["team"] == ["garchomp"]
    assert state["locked_members"] == ["garchomp"]
    assert state["moves_garchomp"] == ["earthquake"]
    assert "moves_dragonite" not in state
    assert state["opponent_team"] == ["ferrothorn"]
    assert state["team_state"] == snapshot


def test_reconcile_preserves_retained_build_and_removes_stale_state():
    state = {
        "team": ["garchomp", "dragonite"],
        "locked_members": ["garchomp", "tyranitar"],
        "moves_garchomp": ["earthquake"],
        "moves_tyranitar": ["crunch"],
    }

    snapshot = reconcile_team(state)

    assert state["locked_members"] == ["garchomp"]
    assert "moves_tyranitar" not in state
    assert snapshot.members[0].moves == ("earthquake",)
    assert snapshot.members[1].moves == ()
    assert state["team_state"] == snapshot


def test_restore_move_lists_are_independent_of_snapshot():
    snapshot = TeamState(members=(TeamMember("garchomp", moves=("earthquake",)),))
    state = {}

    restore_team(state, snapshot)
    state["moves_garchomp"].append("dragon-claw")

    assert snapshot.members[0].moves == ("earthquake",)


def test_empty_team_reconciliation_clears_member_state():
    state = {
        "team": [],
        "locked_members": ["garchomp"],
        "moves_garchomp": ["earthquake"],
    }

    snapshot = reconcile_team(state)

    assert snapshot == TeamState()
    assert state["locked_members"] == []
    assert "moves_garchomp" not in state
