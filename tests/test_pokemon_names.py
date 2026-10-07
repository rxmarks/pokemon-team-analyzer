import pytest

from pokedex.pokemon_names import (
    SHOWDOWN_NAMES,
    resolve_species,
    showdown_species_name,
    species_identifier,
)


@pytest.mark.parametrize(
    ("identifier", "expected"),
    [
        ("nidoran-f", "Nidoran-F"),
        ("nidoran-m", "Nidoran-M"),
        ("mr-mime", "Mr. Mime"),
        ("farfetchd", "Farfetch’d"),
        ("type-null", "Type: Null"),
        ("rotom-wash", "Rotom-Wash"),
    ],
)
def test_explicit_showdown_names(identifier, expected):
    assert showdown_species_name(identifier) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Nidoran♀", "nidoran-f"),
        ("Nidoran♂", "nidoran-m"),
        ("Nidoran-F", "nidoran-f"),
        ("Nidoran-M", "nidoran-m"),
        ("Mr. Mime", "mr-mime"),
        ("MrMime", "mr-mime"),
        ("Farfetch'd", "farfetchd"),
        ("Farfetch’d", "farfetchd"),
        ("Type: Null", "type-null"),
        ("TypeNull", "type-null"),
        ("Rotom-Wash", "rotom-wash"),
        ("Rotom Wash", "rotom-wash"),
        ("RotomWash", "rotom-wash"),
        ("  ROTOM_WASH  ", "rotom-wash"),
    ],
)
def test_supported_species_spellings(name, expected):
    assert species_identifier(name) == expected


@pytest.mark.parametrize(
    "identifier",
    list(SHOWDOWN_NAMES),
)
def test_explicit_names_round_trip(identifier):
    external = showdown_species_name(identifier)

    assert species_identifier(external) == identifier


def test_gender_distinguished_species_remain_distinct():
    assert species_identifier("Nidoran♀") != species_identifier("Nidoran♂")


def test_bare_nidoran_is_not_guessed():
    assert (
        resolve_species(
            "Nidoran",
            {"nidoran-f", "nidoran-m"},
        )
        is None
    )


def test_alias_must_be_available():
    assert resolve_species("RotomWash", {"rotom-wash"}) == "rotom-wash"
    assert resolve_species("RotomWash", {"rotom"}) is None


def test_unknown_form_is_not_replaced_with_base_species():
    assert species_identifier("Rotom-Custom") == "rotom-custom"
    assert resolve_species("Rotom-Custom", {"rotom", "rotom-wash"}) is None


def test_typo_is_not_fuzzy_matched():
    assert resolve_species("Garchom", {"garchomp"}) is None


def test_ordinary_name_uses_normalized_identifier():
    assert species_identifier("  Great   Tusk ") == "great-tusk"
    assert resolve_species("Garchomp", {"garchomp"}) == "garchomp"


def test_unmapped_custom_identifier_is_preserved():
    assert species_identifier("custom-server-form") == "custom-server-form"
    assert (
        resolve_species(
            "custom-server-form",
            {"custom-server-form"},
        )
        == "custom-server-form"
    )


def test_unknown_export_name_uses_readable_fallback():
    assert showdown_species_name("custom-server-form") == "Custom Server Form"


def test_empty_name_does_not_resolve():
    assert species_identifier("   ") == ""
    assert resolve_species("   ", {"garchomp"}) is None


def test_resolution_does_not_modify_available_species():
    valid = {"mr-mime", "rotom-wash"}
    before = set(valid)

    resolve_species("MrMime", valid)

    assert valid == before
