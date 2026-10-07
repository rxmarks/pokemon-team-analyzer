import pytest

from pokedex.pool_import import PoolImportPreview, parse_pool_import

VALID_SPECIES = {
    "garchomp",
    "tyranitar",
    "dragonite",
    "togekiss",
    "gyarados",
    "ferrothorn",
    "pikachu",
    "mr-mime",
    "farfetchd",
    "flabebe",
    "type-null",
}


def test_names_accept_commas_newlines_and_preserve_order():
    preview = parse_pool_import(
        " Garchomp \r\nTyranitar, Dragonite\nTogekiss",
        VALID_SPECIES,
    )

    assert preview.recognized == (
        "garchomp",
        "tyranitar",
        "dragonite",
        "togekiss",
    )
    assert preview.duplicates == ()
    assert preview.unrecognized == ()


def test_names_normalize_display_names():
    preview = parse_pool_import(
        "Mr. Mime, Farfetch’d, Flabébé, Type: Null",
        VALID_SPECIES,
    )

    assert preview.recognized == (
        "mr-mime",
        "farfetchd",
        "flabebe",
        "type-null",
    )


def test_duplicates_are_reported_once():
    preview = parse_pool_import(
        "Garchomp, garchomp, GARCHOMP, Tyranitar, tyranitar",
        VALID_SPECIES,
    )

    assert preview.recognized == ("garchomp", "tyranitar")
    assert preview.duplicates == ("garchomp", "tyranitar")


def test_unknown_names_preserve_first_spelling_without_guessing():
    preview = parse_pool_import(
        "Missingno, missingno, Garchom, Garchomp",
        VALID_SPECIES,
    )

    assert preview.recognized == ("garchomp",)
    assert preview.unrecognized == ("Missingno", "Garchom")
    assert preview.duplicates == ()


def test_names_pool_is_not_limited_to_six():
    names = [
        "garchomp",
        "tyranitar",
        "dragonite",
        "togekiss",
        "gyarados",
        "ferrothorn",
        "pikachu",
    ]

    preview = parse_pool_import(", ".join(names), VALID_SPECIES)

    assert preview.recognized == tuple(names)


def test_showdown_extracts_species_and_ignores_build_details():
    contents = """\
=== [gen9ou] Collection ===

Chompy (Garchomp) (M) @ Choice Scarf
Ability: Rough Skin
- Earthquake

Tyranitar @ Leftovers
- Crunch

Garchomp @ Life Orb
- Swords Dance

Missingno @ Nothing
- Tackle
"""

    preview = parse_pool_import(
        contents,
        VALID_SPECIES,
        input_format="showdown",
    )

    assert preview.recognized == ("garchomp", "tyranitar")
    assert preview.duplicates == ("garchomp",)
    assert preview.unrecognized == ("missingno",)


def test_showdown_pool_is_not_limited_to_six():
    names = [
        "garchomp",
        "tyranitar",
        "dragonite",
        "togekiss",
        "gyarados",
        "ferrothorn",
        "pikachu",
    ]
    contents = "\n\n".join(f"{name} @ Leftovers\n- Tackle" for name in names)

    preview = parse_pool_import(
        contents,
        VALID_SPECIES,
        input_format="showdown",
    )

    assert preview.recognized == tuple(names)


@pytest.mark.parametrize("input_format", ["names", "showdown"])
def test_empty_input_returns_empty_preview(input_format):
    preview = parse_pool_import(
        " \r\n\n ",
        VALID_SPECIES,
        input_format=input_format,
    )

    assert preview == PoolImportPreview()


def test_no_recognized_species_still_provides_feedback():
    preview = parse_pool_import(
        "Missingno, Not A Pokemon",
        VALID_SPECIES,
    )

    assert preview.recognized == ()
    assert preview.unrecognized == ("Missingno", "Not A Pokemon")


def test_does_not_modify_valid_species():
    valid = set(VALID_SPECIES)
    before = set(valid)

    parse_pool_import("Garchomp, Missingno", valid)

    assert valid == before


def test_rejects_unknown_input_format():
    with pytest.raises(ValueError, match="input_format"):
        parse_pool_import(
            "Garchomp",
            VALID_SPECIES,
            input_format="invalid",  # type: ignore[arg-type]
        )
