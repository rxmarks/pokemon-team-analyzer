from dataclasses import FrozenInstanceError

import pytest

from pokedex.config import MAX_MOVES, MAX_TEAM_SIZE
from pokedex.showdown import parse_showdown
from pokedex.team_state import TeamMember, TeamState


def test_member_defaults():
    member = TeamMember("garchomp")

    assert member.species == "garchomp"
    assert member.moves == ()
    assert member.locked is False


def test_member_is_immutable():
    member = TeamMember("garchomp")

    with pytest.raises(FrozenInstanceError):
        setattr(member, "species", "tyranitar")


@pytest.mark.parametrize(
    "species",
    ["", "Garchomp", " mr-mime", "mr mime", "pikachu-", "../pikachu"],
)
def test_member_rejects_invalid_species_identifiers(species):
    with pytest.raises(ValueError, match="Species"):
        TeamMember(species)


def test_member_rejects_too_many_moves():
    moves = tuple(f"move-{index}" for index in range(MAX_MOVES + 1))

    with pytest.raises(ValueError, match="at most"):
        TeamMember("garchomp", moves=moves)


def test_member_rejects_duplicate_moves():
    with pytest.raises(ValueError, match="duplicate moves"):
        TeamMember("garchomp", moves=("earthquake", "earthquake"))


def test_member_rejects_invalid_move_identifier():
    with pytest.raises(ValueError, match="Move"):
        TeamMember("garchomp", moves=("Ice Beam",))


def test_empty_team_is_valid():
    state = TeamState()

    assert state.members == ()
    assert state.species == ()
    assert state.locked_members == frozenset()
    assert state.to_analysis_team({}) == {}


def test_team_preserves_order_and_locks():
    state = TeamState(
        members=(
            TeamMember("tyranitar", locked=True),
            TeamMember("garchomp"),
        )
    )

    assert state.species == ("tyranitar", "garchomp")
    assert state.locked_members == frozenset({"tyranitar"})


def test_team_rejects_duplicate_species():
    with pytest.raises(ValueError, match="duplicate species"):
        TeamState(
            members=(
                TeamMember("garchomp"),
                TeamMember("garchomp", moves=("earthquake",)),
            )
        )


def test_team_rejects_too_many_members():
    members = tuple(TeamMember(f"species-{index}") for index in range(MAX_TEAM_SIZE + 1))

    with pytest.raises(ValueError, match="at most"):
        TeamState(members=members)


def test_analysis_adapter_preserves_member_order():
    state = TeamState(
        members=(
            TeamMember("tyranitar"),
            TeamMember("garchomp"),
        )
    )
    types = {
        "garchomp": ["dragon", "ground"],
        "tyranitar": ["rock", "dark"],
        "pikachu": ["electric"],
    }

    result = state.to_analysis_team(types)

    assert list(result) == ["tyranitar", "garchomp"]
    assert result == {
        "tyranitar": ["rock", "dark"],
        "garchomp": ["dragon", "ground"],
    }


def test_analysis_adapter_does_not_share_mutable_type_lists():
    state = TeamState(members=(TeamMember("garchomp"),))
    source = {"garchomp": ["dragon", "ground"]}

    result = state.to_analysis_team(source)
    result["garchomp"].append("water")

    assert source["garchomp"] == ["dragon", "ground"]


def test_analysis_adapter_rejects_missing_types():
    state = TeamState(members=(TeamMember("garchomp"),))

    with pytest.raises(ValueError, match="Missing types"):
        state.to_analysis_team({})


def test_analysis_adapter_rejects_empty_types():
    state = TeamState(members=(TeamMember("garchomp"),))

    with pytest.raises(ValueError, match="Empty types"):
        state.to_analysis_team({"garchomp": []})


def test_showdown_conversion_preserves_species_and_moves():
    parsed = parse_showdown(
        "Garchomp @ Life Orb\n- Earthquake\n- Dragon Claw\n\nTyranitar\n- Crunch\n"
    )

    state = TeamState.from_showdown(parsed)

    assert state.species == ("garchomp", "tyranitar")
    assert state.members[0].moves == ("earthquake", "dragon-claw")
    assert state.members[1].moves == ("crunch",)
    assert state.locked_members == frozenset()


def test_showdown_conversion_copies_parser_move_lists():
    parsed = parse_showdown("Garchomp\n- Earthquake")
    state = TeamState.from_showdown(parsed)

    parsed[0].moves.append("dragon-claw")

    assert state.members[0].moves == ("earthquake",)


def test_showdown_conversion_rejects_duplicate_members():
    parsed = parse_showdown("Garchomp\n\nGarchomp")

    with pytest.raises(ValueError, match="duplicate species"):
        TeamState.from_showdown(parsed)
