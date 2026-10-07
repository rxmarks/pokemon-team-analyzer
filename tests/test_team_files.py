import json

import pytest

from pokedex.config import MAX_MOVES, MAX_TEAM_SIZE
from pokedex.team_files import MAX_FILE_BYTES, dump_team, load_team
from pokedex.team_state import TeamMember, TeamState


def document_with(member):
    return json.dumps({"schema_version": 1, "team": [member]})


def valid_member():
    return {
        "species": "garchomp",
        "moves": ["earthquake", "swords-dance"],
        "locked": True,
    }


def test_round_trip_preserves_supported_build():
    state = TeamState(
        members=(
            TeamMember(
                "garchomp",
                moves=("earthquake", "swords-dance"),
                locked=True,
            ),
            TeamMember("tyranitar", moves=("crunch",)),
        )
    )

    assert load_team(dump_team(state)) == state


def test_empty_team_round_trips():
    state = TeamState()

    assert load_team(dump_team(state)) == state


def test_serialization_declares_version_and_supported_fields():
    state = TeamState(members=(TeamMember("garchomp"),))
    document = json.loads(dump_team(state))

    assert document == {
        "schema_version": 1,
        "team": [
            {
                "species": "garchomp",
                "moves": [],
                "locked": False,
            }
        ],
    }


def test_load_accepts_utf8_bytes_and_bom():
    state = TeamState(members=(TeamMember("garchomp"),))
    contents = dump_team(state)

    assert load_team(contents.encode("utf-8")) == state
    assert load_team(("\ufeff" + contents).encode("utf-8")) == state
    assert load_team("\ufeff" + contents) == state


@pytest.mark.parametrize("contents", ["", "{", "not json", '{"team":'])
def test_load_rejects_invalid_json(contents):
    with pytest.raises(ValueError, match="valid JSON"):
        load_team(contents)


@pytest.mark.parametrize("contents", ["[]", "null", "123", '"team"'])
def test_load_rejects_non_object_root(contents):
    with pytest.raises(ValueError, match="JSON object"):
        load_team(contents)


@pytest.mark.parametrize("version", [2, 0, "1", True, 1.0, None])
def test_load_rejects_unsupported_version(version):
    contents = json.dumps({"schema_version": version, "team": []})

    with pytest.raises(ValueError, match="schema version"):
        load_team(contents)


def test_load_rejects_unknown_root_fields():
    contents = json.dumps({"schema_version": 1, "team": [], "opponents": []})

    with pytest.raises(ValueError, match="contain only"):
        load_team(contents)


def test_load_rejects_non_list_team():
    contents = json.dumps({"schema_version": 1, "team": {}})

    with pytest.raises(ValueError, match="must be a list"):
        load_team(contents)


def test_load_rejects_non_object_member():
    contents = json.dumps({"schema_version": 1, "team": ["garchomp"]})

    with pytest.raises(ValueError, match="must be an object"):
        load_team(contents)


def test_load_rejects_unknown_member_fields():
    member = valid_member()
    member["item"] = "life-orb"

    with pytest.raises(ValueError, match="contain only"):
        load_team(document_with(member))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("species", 25, "species must be a string"),
        ("moves", "earthquake", "list of strings"),
        ("moves", [123], "list of strings"),
        ("locked", "true", "locked must be a boolean"),
        ("species", "Garchomp", "identifier"),
        ("moves", ["Ice Beam"], "identifier"),
        ("moves", ["earthquake", "earthquake"], "duplicate moves"),
    ],
)
def test_load_rejects_invalid_member_fields(field, value, message):
    member = valid_member()
    member[field] = value

    with pytest.raises(ValueError, match=message):
        load_team(document_with(member))


def test_load_rejects_too_many_moves():
    member = valid_member()
    member["moves"] = [f"move-{index}" for index in range(MAX_MOVES + 1)]

    with pytest.raises(ValueError, match="at most"):
        load_team(document_with(member))


def test_load_rejects_duplicate_species():
    contents = json.dumps({"schema_version": 1, "team": [valid_member(), valid_member()]})

    with pytest.raises(ValueError, match="duplicate species"):
        load_team(contents)


def test_load_rejects_too_many_members():
    members = [
        {
            "species": f"species-{index}",
            "moves": [],
            "locked": False,
        }
        for index in range(MAX_TEAM_SIZE + 1)
    ]
    contents = json.dumps({"schema_version": 1, "team": members})

    with pytest.raises(ValueError, match="at most"):
        load_team(contents)


def test_load_validates_species_when_requested():
    contents = document_with(valid_member())

    with pytest.raises(ValueError, match="unrecognized species"):
        load_team(contents, valid_species={"tyranitar"})

    state = load_team(contents, valid_species={"garchomp"})
    assert state.species == ("garchomp",)


def test_load_preserves_unverified_move_identifiers():
    member = valid_member()
    member["moves"] = ["unverified-move"]

    state = load_team(document_with(member))

    assert state.members[0].moves == ("unverified-move",)


def test_load_rejects_duplicate_json_keys():
    contents = '{"schema_version": 1, "schema_version": 1, "team": []}'

    with pytest.raises(ValueError, match="Duplicate JSON key"):
        load_team(contents)


def test_load_rejects_duplicate_member_keys():
    contents = (
        '{"schema_version": 1, "team": ['
        '{"species": "garchomp", "species": "tyranitar", '
        '"moves": [], "locked": false}]}'
    )

    with pytest.raises(ValueError, match="Duplicate JSON key"):
        load_team(contents)


@pytest.mark.parametrize(
    "contents",
    [
        pytest.param(
            " " * (MAX_FILE_BYTES + 1),
            id="oversized-text",
        ),
        pytest.param(
            b" " * (MAX_FILE_BYTES + 1),
            id="oversized-bytes",
        ),
    ],
)
def test_load_rejects_oversized_files(contents):
    with pytest.raises(ValueError, match="size limit"):
        load_team(contents)


def test_load_rejects_invalid_utf8():
    with pytest.raises(ValueError, match="UTF-8"):
        load_team(b"\xff")


def test_dump_does_not_mutate_state():
    state = TeamState(members=(TeamMember("garchomp", moves=("earthquake",), locked=True),))
    before = state

    dump_team(state)

    assert state == before
    assert state.members[0].moves == ("earthquake",)
