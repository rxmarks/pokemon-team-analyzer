"""Parse replacement-pool input without changing application state."""

import re
from collections.abc import Collection
from dataclasses import dataclass
from typing import Literal

from pokedex.showdown import normalize, parse_showdown

PoolInputFormat = Literal["names", "showdown"]


@dataclass(frozen=True)
class PoolImportPreview:
    recognized: tuple[str, ...] = ()
    duplicates: tuple[str, ...] = ()
    unrecognized: tuple[str, ...] = ()


def parse_pool_import(
    contents: str,
    valid_species: Collection[str],
    *,
    input_format: PoolInputFormat = "names",
) -> PoolImportPreview:
    """Return recognized species and feedback in first-seen order."""
    if input_format == "names":
        entries = [entry.strip() for entry in re.split(r"[,\r\n]+", contents) if entry.strip()]
    elif input_format == "showdown":
        entries = [mon.species for mon in parse_showdown(contents, max_members=None)]
    else:
        raise ValueError("input_format must be 'names' or 'showdown'.")

    valid = set(valid_species)
    recognized: list[str] = []
    duplicates: list[str] = []
    unrecognized: list[str] = []

    seen_valid: set[str] = set()
    seen_duplicates: set[str] = set()
    seen_unrecognized: set[str] = set()

    for entry in entries:
        species = normalize(entry)

        if species not in valid:
            if species not in seen_unrecognized:
                unrecognized.append(entry)
                seen_unrecognized.add(species)
            continue

        if species in seen_valid:
            if species not in seen_duplicates:
                duplicates.append(species)
                seen_duplicates.add(species)
            continue

        recognized.append(species)
        seen_valid.add(species)

    return PoolImportPreview(
        recognized=tuple(recognized),
        duplicates=tuple(duplicates),
        unrecognized=tuple(unrecognized),
    )
