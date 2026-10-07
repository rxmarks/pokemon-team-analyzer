"""Explicit species-name translation without changing stored identifiers."""

import re
import unicodedata
from collections.abc import Collection

SHOWDOWN_NAMES: dict[str, str] = {
    "nidoran-f": "Nidoran-F",
    "nidoran-m": "Nidoran-M",
    "mr-mime": "Mr. Mime",
    "farfetchd": "Farfetch’d",
    "type-null": "Type: Null",
    "rotom-wash": "Rotom-Wash",
}


def _species_key(name: str) -> str:
    """Normalize species spelling while preserving meaningful gender symbols."""
    value = name.strip().lower()
    value = value.replace("♀", "-f").replace("♂", "-m")
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode()
    value = re.sub(r"[.':%]", "", value)
    value = re.sub(r"[\s_]+", "-", value)
    return re.sub(r"-+", "-", value).strip("-")


_ALIASES: dict[str, str] = {}

for _identifier, _external_name in SHOWDOWN_NAMES.items():
    _ALIASES[_species_key(_external_name)] = _identifier
    _ALIASES[_species_key(_identifier)] = _identifier
    _ALIASES[_species_key(_external_name).replace("-", "")] = _identifier


def species_identifier(name: str) -> str:
    """Translate supported species spellings to an internal identifier.

    Unknown names are normalized but not guessed or replaced with a base form.
    """
    key = _species_key(name)
    return _ALIASES.get(key, key)


def resolve_species(
    name: str,
    valid_species: Collection[str],
) -> str | None:
    """Resolve a supported spelling only when its identifier is available."""
    identifier = species_identifier(name)
    return identifier if identifier in valid_species else None


def showdown_species_name(identifier: str) -> str:
    """Return an explicit Showdown name, or an unverified readable fallback."""
    return SHOWDOWN_NAMES.get(
        identifier,
        identifier.replace("-", " ").title(),
    )
