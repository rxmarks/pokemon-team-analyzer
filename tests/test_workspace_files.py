import json

import pytest

from pokedex.config import MAX_TEAM_SIZE
from pokedex.team_files import dump_team
from pokedex.team_state import TeamMember, TeamState
from pokedex.workspace_files import (
    DOCUMENT_TYPE,
    MAX_FILE_BYTES,
    WorkspaceState,
    dump_workspace,
    load_workspace,
)


def sample_workspace():
    return WorkspaceState(
        team=TeamState(
            members=(
                TeamMember(
                    "garchomp",
                    moves=("earthquake", "swords-dance"),
                    locked=True,
                ),
                TeamMember("tyranitar", moves=("crunch",)),
            )
        ),
        available_pokemon=("togekiss", "dragonite", "ferrothorn"),
        candidate_source="custom",
        opponent_team=("gyarados", "ferrothorn"),
        matchup_improvements_only=False,
    )


def sample_document():
    return json.loads(dump_workspace(sample_workspace()))


def test_round_trip_preserves_build_order_and_settings():
    state = sample_workspace()

    assert load_workspace(dump_workspace(state)) == state


def test_empty_workspace_round_trips():
    state = WorkspaceState()

    assert load_workspace(dump_workspace(state)) == state


def test_custom_source_with_empty_pool_round_trips():
    state = WorkspaceState(candidate_source="custom")

    assert load_workspace(dump_workspace(state)) == state


def test_document_identifies_workspace_and_nested_team_version():
    document = sample_document()

    assert document["document_type"] == DOCUMENT_TYPE
    assert document["schema_version"] == 1
    assert document["team_document"]["schema_version"] == 1
    assert set(document) == {
        "document_type",
        "schema_version",
        "team_document",
        "available_pokemon",
        "candidate_source",
        "opponent_team",
        "matchup_improvements_only",
    }


def test_pool_larger_than_six_round_trips():
    names = tuple(f"species-{index}" for index in range(20))
    state = WorkspaceState(available_pokemon=names)

    assert (
        load_workspace(
            dump_workspace(state),
            valid_species=set(names),
        )
        == state
    )


def test_species_can_overlap_across_lists():
    state = WorkspaceState(
        team=TeamState(members=(TeamMember("garchomp"),)),
        available_pokemon=("garchomp",),
        opponent_team=("garchomp",),
    )

    assert load_workspace(dump_workspace(state)) == state


@pytest.mark.parametrize(
    "encoding",
    ["text-bom", "bytes", "bytes-bom"],
)
def test_accepts_utf8_and_bom(encoding):
    state = sample_workspace()
    text = dump_workspace(state)

    if encoding == "text-bom":
        contents = "\ufeff" + text
    elif encoding == "bytes":
        contents = text.encode("utf-8")
    else:
        contents = ("\ufeff" + text).encode("utf-8")

    assert load_workspace(contents) == state


@pytest.mark.parametrize("contents", ["", "{", "not json"])
def test_rejects_invalid_json(contents):
    with pytest.raises(ValueError, match="valid JSON"):
        load_workspace(contents)


@pytest.mark.parametrize("contents", ["[]", "null", "123"])
def test_rejects_non_object_root(contents):
    with pytest.raises(ValueError, match="JSON object"):
        load_workspace(contents)


def test_rejects_team_only_file_with_helpful_message():
    with pytest.raises(ValueError, match="team JSON loader"):
        load_workspace(dump_team(TeamState()))


def test_rejects_wrong_document_type():
    document = sample_document()
    document["document_type"] = "another-app"

    with pytest.raises(ValueError, match="not a workspace"):
        load_workspace(json.dumps(document))


@pytest.mark.parametrize("version", [0, 2, "1", True, 1.0, None])
def test_rejects_unsupported_workspace_version(version):
    document = sample_document()
    document["schema_version"] = version

    with pytest.raises(ValueError, match="workspace schema version"):
        load_workspace(json.dumps(document))


@pytest.mark.parametrize("change", ["missing", "extra"])
def test_rejects_missing_or_extra_fields(change):
    document = sample_document()

    if change == "missing":
        document.pop("candidate_source")
    else:
        document["pending_swap"] = ["garchomp", "dragonite"]

    with pytest.raises(ValueError, match="missing or unsupported"):
        load_workspace(json.dumps(document))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("available_pokemon", "dragonite", "list of strings"),
        ("available_pokemon", [123], "list of strings"),
        ("available_pokemon", ["Dragonite"], "identifier"),
        (
            "available_pokemon",
            ["dragonite", "dragonite"],
            "duplicate species",
        ),
        ("opponent_team", None, "list of strings"),
        ("opponent_team", ["gyarados", "gyarados"], "duplicate species"),
        ("candidate_source", "My available Pokémon", "Candidate source"),
        ("candidate_source", [], "Candidate source"),
        ("matchup_improvements_only", "false", "boolean"),
        ("matchup_improvements_only", 1, "boolean"),
    ],
)
def test_rejects_invalid_workspace_fields(field, value, message):
    document = sample_document()
    document[field] = value

    with pytest.raises(ValueError, match=message):
        load_workspace(json.dumps(document))


def test_rejects_too_many_opponents():
    document = sample_document()
    document["opponent_team"] = [f"species-{index}" for index in range(MAX_TEAM_SIZE + 1)]

    with pytest.raises(ValueError, match="Opponent team can have at most"):
        load_workspace(json.dumps(document))


@pytest.mark.parametrize(
    "problem",
    ["too-many", "duplicates", "invalid-move", "version", "wrong-type"],
)
def test_reuses_nested_team_validation(problem):
    document = sample_document()
    nested = document["team_document"]

    if problem == "too-many":
        nested["team"] = [
            {
                "species": f"species-{index}",
                "moves": [],
                "locked": False,
            }
            for index in range(MAX_TEAM_SIZE + 1)
        ]
    elif problem == "duplicates":
        nested["team"] = [nested["team"][0], nested["team"][0]]
    elif problem == "invalid-move":
        nested["team"][0]["moves"] = ["Ice Beam"]
    elif problem == "version":
        nested["schema_version"] = 2
    else:
        document["team_document"] = []

    with pytest.raises(ValueError, match="Workspace team"):
        load_workspace(json.dumps(document))


@pytest.mark.parametrize("location", ["team", "pool", "opponents"])
def test_validates_species_in_every_location(location):
    document = json.loads(dump_workspace(WorkspaceState()))

    if location == "team":
        document["team_document"]["team"] = [{"species": "missingno", "moves": [], "locked": False}]
    elif location == "pool":
        document["available_pokemon"] = ["missingno"]
    else:
        document["opponent_team"] = ["missingno"]

    with pytest.raises(ValueError, match="unrecognized species"):
        load_workspace(
            json.dumps(document),
            valid_species={"garchomp"},
        )


def test_accepts_recognized_species():
    state = sample_workspace()
    valid = set(state.team.species) | set(state.available_pokemon) | set(state.opponent_team)

    assert load_workspace(dump_workspace(state), valid_species=valid) == state


def test_rejects_duplicate_root_keys():
    contents = dump_workspace(WorkspaceState()).replace(
        '"schema_version": 1',
        '"schema_version": 1, "schema_version": 1',
        1,
    )

    with pytest.raises(ValueError, match="Duplicate JSON key"):
        load_workspace(contents)


def test_rejects_duplicate_nested_keys():
    contents = dump_workspace(sample_workspace()).replace(
        '"locked": true',
        '"locked": true, "locked": false',
        1,
    )

    with pytest.raises(ValueError, match="Duplicate JSON key"):
        load_workspace(contents)


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
def test_rejects_oversized_input(contents):
    with pytest.raises(ValueError, match="size limit"):
        load_workspace(contents)


def test_rejects_invalid_utf8():
    with pytest.raises(ValueError, match="UTF-8"):
        load_workspace(b"\xff")


def test_dump_rejects_oversized_workspace():
    state = WorkspaceState(available_pokemon=("a" * MAX_FILE_BYTES,))

    with pytest.raises(ValueError, match="size limit"):
        dump_workspace(state)


def test_dump_does_not_mutate_workspace():
    state = sample_workspace()
    before_team = state.team
    before_pool = state.available_pokemon
    before_opponents = state.opponent_team

    contents = dump_workspace(state)

    assert state.team == before_team
    assert state.available_pokemon == before_pool
    assert state.opponent_team == before_opponents
    assert load_workspace(contents) == state
