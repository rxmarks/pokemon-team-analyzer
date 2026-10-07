from copy import deepcopy

import pytest

from pokedex.export import showdown_export
from pokedex.showdown import parse_showdown
from pokedex.team_state import TeamMember, TeamState


def test_export_has_one_block_per_pokemon():
    team = {
        "garchomp": ["dragon", "ground"],
        "gengar": ["ghost", "poison"],
    }

    result = showdown_export(team)

    assert result == "Garchomp\n\nGengar\n"


def test_export_includes_suggested_moves():
    team = {"garchomp": ["dragon", "ground"]}
    moves = {"garchomp": ["earthquake", "dragon-claw"]}

    result = showdown_export(team, moves)

    assert result == "Garchomp\n- Earthquake\n- Dragon Claw\n"


def test_export_omits_missing_move_sets():
    team = {
        "garchomp": ["dragon", "ground"],
        "gengar": ["ghost", "poison"],
    }
    moves = {"garchomp": ["earthquake"]}

    result = showdown_export(team, moves)

    assert "Garchomp\n- Earthquake" in result
    assert "\n\nGengar\n" in result


def test_empty_team_exports_empty_text():
    assert showdown_export({}) == ""
    assert showdown_export(TeamState()) == ""


def test_structured_export_preserves_team_and_move_order():
    state = TeamState(
        members=(
            TeamMember(
                "tyranitar",
                moves=("crunch", "ice-beam"),
            ),
            TeamMember(
                "garchomp",
                moves=("swords-dance", "earthquake", "unverified-move"),
                locked=True,
            ),
        )
    )

    assert showdown_export(state) == (
        "Tyranitar\n"
        "- Crunch\n"
        "- Ice Beam\n"
        "\n"
        "Garchomp\n"
        "- Swords Dance\n"
        "- Earthquake\n"
        "- Unverified Move\n"
    )


def test_structured_export_includes_members_without_moves():
    state = TeamState(
        members=(
            TeamMember("garchomp", moves=("earthquake",)),
            TeamMember("tyranitar"),
        )
    )

    assert showdown_export(state) == ("Garchomp\n- Earthquake\n\nTyranitar\n")


@pytest.mark.parametrize(
    "species",
    [
        "garchomp",
        "mr-mime",
        "farfetchd",
        "type-null",
        "rotom-wash",
        "nidoran-f",
    ],
)
def test_structured_export_round_trips_through_app_parser(species):
    state = TeamState(
        members=(
            TeamMember(
                species,
                moves=("earthquake", "swords-dance", "unverified-move"),
            ),
        )
    )

    parsed = parse_showdown(showdown_export(state))

    assert len(parsed) == 1
    assert parsed[0].species == species
    assert parsed[0].moves == [
        "earthquake",
        "swords-dance",
        "unverified-move",
    ]


def test_export_does_not_mutate_structured_or_legacy_inputs():
    state = TeamState(
        members=(
            TeamMember(
                "garchomp",
                moves=("earthquake",),
                locked=True,
            ),
        )
    )
    team = {"garchomp": ["dragon", "ground"]}
    moves = {"garchomp": ["earthquake", "swords-dance"]}
    before_team = deepcopy(team)
    before_moves = deepcopy(moves)

    showdown_export(state)
    showdown_export(team, moves)

    assert state.members[0].moves == ("earthquake",)
    assert state.members[0].locked is True
    assert team == before_team
    assert moves == before_moves


def test_structured_export_rejects_competing_move_source():
    state = TeamState(members=(TeamMember("garchomp", moves=("earthquake",)),))

    with pytest.raises(ValueError, match="separate move sets"):
        showdown_export(state, {"garchomp": ["ice-beam"]})
