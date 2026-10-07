import re
import unicodedata
from dataclasses import dataclass, field

from pokedex.config import MAX_MOVES, MAX_TEAM_SIZE
from pokedex.pokemon_names import species_identifier

_GENDER = re.compile(r"\s*\((?:M|F)\)\s*$")
_SPECIES_IN_PARENS = re.compile(r"\(([^()]+)\)\s*$")
_BRACKETS = re.compile(r"\s*\[.*?\]")


@dataclass(frozen=True)
class ShowdownMon:
    species: str
    moves: list[str] = field(default_factory=list)


def normalize(name: str) -> str:
    """Turn a Showdown name into a PokeAPI-style name, e.g. 'Mr. Mime' -> 'mr-mime'."""
    s = unicodedata.normalize("NFKD", name.strip().lower())
    s = s.encode("ascii", "ignore").decode()
    s = re.sub(r"[.':%]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")


def _parse_block(lines: list[str]) -> ShowdownMon | None:
    header = lines[0]
    if header.startswith("==="):
        return None
    header = header.split(" @ ")[0]
    header = _GENDER.sub("", header)
    match = _SPECIES_IN_PARENS.search(header)
    species = match.group(1) if match else header
    species = species_identifier(species)
    moves = [normalize(_BRACKETS.sub("", line[1:])) for line in lines[1:] if line.startswith("-")]
    return ShowdownMon(species=species_identifier(species), moves=moves[:MAX_MOVES])


def parse_showdown(
    paste: str,
    *,
    max_members: int | None = MAX_TEAM_SIZE,
) -> list[ShowdownMon]:
    """Parse an export, defaulting to the team limit; None keeps all members."""
    if max_members is not None and max_members < 0:
        raise ValueError("max_members must be nonnegative or None.")

    blocks: list[list[str]] = []
    current: list[str] = []

    for raw in paste.splitlines():
        line = raw.strip()
        if line:
            current.append(line)
        elif current:
            blocks.append(current)
            current = []

    if current:
        blocks.append(current)

    team = [mon for block in blocks if (mon := _parse_block(block)) is not None]

    return team if max_members is None else team[:max_members]
