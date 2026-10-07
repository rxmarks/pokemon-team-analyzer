"""Versioned JSON serialization for supported main-team state."""

import json
from typing import Any

from pokedex.team_state import TeamMember, TeamState

SCHEMA_VERSION = 1
MAX_FILE_BYTES = 64 * 1024


def dump_team(state: TeamState) -> str:
    """Serialize a supported team build as readable, versioned JSON."""
    document = {
        "schema_version": SCHEMA_VERSION,
        "team": [
            {
                "species": member.species,
                "moves": list(member.moves),
                "locked": member.locked,
            }
            for member in state.members
        ],
    }

    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject duplicate JSON keys rather than silently keeping the last value."""
    result: dict[str, Any] = {}

    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: '{key}'.")
        result[key] = value

    return result


def load_team(
    contents: str | bytes,
    *,
    valid_species: set[str] | None = None,
) -> TeamState:
    """Validate a complete document before returning a new team snapshot."""
    if isinstance(contents, bytes):
        if len(contents) > MAX_FILE_BYTES:
            raise ValueError("Team file exceeds the 64 KiB size limit.")

        try:
            text = contents.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("Team file must be UTF-8 encoded.") from exc
    else:
        if len(contents.encode("utf-8")) > MAX_FILE_BYTES:
            raise ValueError("Team file exceeds the 64 KiB size limit.")

        text = contents.removeprefix("\ufeff")

    try:
        document = json.loads(text, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Team file must contain valid JSON.") from exc

    if not isinstance(document, dict):
        raise ValueError("Team file must contain a JSON object.")

    if set(document) != {"schema_version", "team"}:
        raise ValueError("Team file must contain only 'schema_version' and 'team'.")

    version = document["schema_version"]
    if type(version) is not int or version != SCHEMA_VERSION:
        raise ValueError(f"Unsupported schema version. Expected {SCHEMA_VERSION}.")

    raw_team = document["team"]
    if not isinstance(raw_team, list):
        raise ValueError("'team' must be a list.")

    members: list[TeamMember] = []

    for index, raw_member in enumerate(raw_team, start=1):
        if not isinstance(raw_member, dict):
            raise ValueError(f"Member {index} must be an object.")

        if set(raw_member) != {"species", "moves", "locked"}:
            raise ValueError(f"Member {index} must contain only 'species', 'moves', and 'locked'.")

        species = raw_member["species"]
        moves = raw_member["moves"]
        locked = raw_member["locked"]

        if not isinstance(species, str):
            raise ValueError(f"Member {index}: species must be a string.")

        if not isinstance(moves, list) or any(not isinstance(move, str) for move in moves):
            raise ValueError(f"Member {index}: moves must be a list of strings.")

        if not isinstance(locked, bool):
            raise ValueError(f"Member {index}: locked must be a boolean.")

        try:
            member = TeamMember(
                species=species,
                moves=tuple(moves),
                locked=locked,
            )
        except ValueError as exc:
            raise ValueError(f"Member {index}: {exc}") from exc

        if valid_species is not None and species not in valid_species:
            raise ValueError(f"Member {index}: unrecognized species '{species}'.")

        members.append(member)

    return TeamState(members=tuple(members))
