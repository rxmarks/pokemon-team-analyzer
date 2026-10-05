import re
import unicodedata
from dataclasses import dataclass, field

from pokedex.config import MAX_MOVES, MAX_TEAM_SIZE

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
    moves = [normalize(_BRACKETS.sub("", line[1:])) for line in lines[1:] if line.startswith("-")]
    return ShowdownMon(species=normalize(species), moves=moves[:MAX_MOVES])


def parse_showdown(paste: str) -> list[ShowdownMon]:
    """Parse a Pokémon Showdown team export into at most 6 Pokémon."""
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
    return team[:MAX_TEAM_SIZE]
