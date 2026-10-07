"""Versioned workspace files independent of Streamlit."""

import json
from dataclasses import dataclass, field
from typing import Any

from pokedex.config import MAX_TEAM_SIZE
from pokedex.team_files import dump_team, load_team
from pokedex.team_state import TeamMember, TeamState

DOCUMENT_TYPE = "pokemon-team-analyzer-workspace"
SCHEMA_VERSION = 1
MAX_FILE_BYTES = 256 * 1024
CANDIDATE_SOURCES = ("default", "custom")

_DOCUMENT_FIELDS = {
    "document_type",
    "schema_version",
    "team_document",
    "available_pokemon",
    "candidate_source",
    "opponent_team",
    "matchup_improvements_only",
}


def _validate_species_tuple(values: tuple[str, ...], label: str) -> None:
    if not isinstance(values, tuple):
        raise ValueError(f"{label} must be a tuple.")

    for name in values:
        try:
            TeamMember(species=name)
        except ValueError as exc:
            raise ValueError(f"{label}: {exc}") from exc

    if len(set(values)) != len(values):
        raise ValueError(f"{label} cannot contain duplicate species.")


@dataclass(frozen=True)
class WorkspaceState:
    """Supported team build and persistent analysis preferences."""

    team: TeamState = field(default_factory=TeamState)
    available_pokemon: tuple[str, ...] = ()
    candidate_source: str = "default"
    opponent_team: tuple[str, ...] = ()
    matchup_improvements_only: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.team, TeamState):
            raise ValueError("Team must be a TeamState.")

        _validate_species_tuple(self.available_pokemon, "Available Pokémon")
        _validate_species_tuple(self.opponent_team, "Opponent team")

        if len(self.opponent_team) > MAX_TEAM_SIZE:
            raise ValueError(f"Opponent team can have at most {MAX_TEAM_SIZE} members.")

        if (
            not isinstance(self.candidate_source, str)
            or self.candidate_source not in CANDIDATE_SOURCES
        ):
            raise ValueError("Candidate source must be 'default' or 'custom'.")

        if not isinstance(self.matchup_improvements_only, bool):
            raise ValueError("Matchup improvements setting must be a boolean.")


def dump_workspace(state: WorkspaceState) -> str:
    """Serialize a workspace without changing it."""
    document = {
        "document_type": DOCUMENT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "team_document": json.loads(dump_team(state.team)),
        "available_pokemon": list(state.available_pokemon),
        "candidate_source": state.candidate_source,
        "opponent_team": list(state.opponent_team),
        "matchup_improvements_only": state.matchup_improvements_only,
    }

    contents = json.dumps(document, indent=2, ensure_ascii=False) + "\n"

    if len(contents.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError("Workspace file exceeds the 256 KiB size limit.")

    return contents


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}

    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: '{key}'.")
        result[key] = value

    return result


def _species_list(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(name, str) for name in value):
        raise ValueError(f"{label} must be a list of strings.")

    return tuple(value)


def load_workspace(
    contents: str | bytes,
    *,
    valid_species: set[str] | None = None,
) -> WorkspaceState:
    """Validate the whole file before returning a new immutable workspace."""
    if isinstance(contents, bytes):
        if len(contents) > MAX_FILE_BYTES:
            raise ValueError("Workspace file exceeds the 256 KiB size limit.")

        try:
            text = contents.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("Workspace file must be UTF-8 encoded.") from exc
    else:
        if len(contents.encode("utf-8")) > MAX_FILE_BYTES:
            raise ValueError("Workspace file exceeds the 256 KiB size limit.")

        text = contents.removeprefix("\ufeff")

    try:
        document = json.loads(text, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Workspace file must contain valid JSON.") from exc

    if not isinstance(document, dict):
        raise ValueError("Workspace file must contain a JSON object.")

    if document.get("document_type") != DOCUMENT_TYPE:
        raise ValueError(
            "This is not a workspace file. Use the team JSON loader for team-only files."
        )

    if set(document) != _DOCUMENT_FIELDS:
        raise ValueError(
            "Workspace fields are missing or unsupported. "
            "Expected: " + ", ".join(sorted(_DOCUMENT_FIELDS)) + "."
        )

    version = document["schema_version"]
    if type(version) is not int or version != SCHEMA_VERSION:
        raise ValueError(f"Unsupported workspace schema version. Expected {SCHEMA_VERSION}.")

    try:
        team = load_team(
            json.dumps(document["team_document"]),
            valid_species=valid_species,
        )
    except ValueError as exc:
        raise ValueError(f"Workspace team: {exc}") from exc

    state = WorkspaceState(
        team=team,
        available_pokemon=_species_list(
            document["available_pokemon"],
            "Available Pokémon",
        ),
        candidate_source=document["candidate_source"],
        opponent_team=_species_list(
            document["opponent_team"],
            "Opponent team",
        ),
        matchup_improvements_only=document["matchup_improvements_only"],
    )

    if valid_species is not None:
        for label, names in (
            ("Available Pokémon", state.available_pokemon),
            ("Opponent team", state.opponent_team),
        ):
            for name in names:
                if name not in valid_species:
                    raise ValueError(f"{label}: unrecognized species '{name}'.")

    return state
