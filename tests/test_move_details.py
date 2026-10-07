from copy import deepcopy

import pytest

from pokedex.move_details import selected_move_details


@pytest.fixture
def move_cache():
    return {
        "earthquake": {
            "type": "ground",
            "damage_class": "physical",
            "power": 100,
        },
        "ice-beam": {
            "type": "ice",
            "damage_class": "special",
            "power": 90,
        },
        "swords-dance": {
            "type": "normal",
            "damage_class": "status",
            "power": None,
        },
        "seismic-toss": {
            "type": "fighting",
            "damage_class": "physical",
            "power": None,
        },
    }


def test_physical_move_details(move_cache):
    rows = selected_move_details(["earthquake"], move_cache)

    assert rows == [
        {
            "Move": "Earthquake",
            "Type": "Ground",
            "Category": "Physical",
            "Power": 100,
            "Coverage": "Counted — damaging move type",
        }
    ]


def test_special_move_details(move_cache):
    row = selected_move_details(["ice-beam"], move_cache)[0]

    assert row["Move"] == "Ice Beam"
    assert row["Type"] == "Ice"
    assert row["Category"] == "Special"
    assert row["Power"] == 90
    assert row["Coverage"] == "Counted — damaging move type"


def test_status_move_is_preserved_but_not_counted(move_cache):
    row = selected_move_details(["swords-dance"], move_cache)[0]

    assert row["Category"] == "Status"
    assert row["Power"] is None
    assert row["Coverage"] == "Not counted — status move"


def test_unknown_move_has_explicit_missing_metadata():
    rows = selected_move_details(["unverified-move"], {})

    assert rows == [
        {
            "Move": "Unverified Move",
            "Type": "Unknown",
            "Category": "Unknown",
            "Power": None,
            "Coverage": "Unavailable — selection preserved",
        }
    ]


def test_missing_power_does_not_exclude_damaging_move(move_cache):
    row = selected_move_details(["seismic-toss"], move_cache)[0]

    assert row["Power"] is None
    assert row["Category"] == "Physical"
    assert row["Coverage"] == "Counted — damaging move type"


def test_absent_power_field_is_displayed_as_missing():
    cache = {
        "earthquake": {
            "type": "ground",
            "damage_class": "physical",
        }
    }

    row = selected_move_details(["earthquake"], cache)[0]

    assert row["Power"] is None
    assert row["Coverage"] == "Counted — damaging move type"


def test_preserves_selected_move_order(move_cache):
    moves = ["ice-beam", "unverified-move", "swords-dance", "earthquake"]

    rows = selected_move_details(moves, move_cache)

    assert [row["Move"] for row in rows] == [
        "Ice Beam",
        "Unverified Move",
        "Swords Dance",
        "Earthquake",
    ]


def test_empty_selection_returns_no_rows(move_cache):
    assert selected_move_details([], move_cache) == []


def test_does_not_mutate_moves_or_metadata(move_cache):
    moves = ["earthquake", "swords-dance"]
    before_moves = list(moves)
    before_cache = deepcopy(move_cache)

    selected_move_details(moves, move_cache)

    assert moves == before_moves
    assert move_cache == before_cache
