import pytest

from pokedex.display import (
    FALLBACK_COLOR,
    TYPE_COLORS,
    color_multiplier,
    display_name,
    format_badness_change,
    format_multiplier,
    type_badge,
    type_badges,
)


def test_all_18_types_have_colors():
    assert len(TYPE_COLORS) == 18


def test_display_name_formats_forms():
    assert display_name("garchomp-mega") == "Garchomp Mega"


def test_type_badge_uses_type_color_and_title():
    html = type_badge("fire")
    assert TYPE_COLORS["fire"] in html
    assert ">Fire<" in html


def test_light_types_get_dark_text():
    assert "color:#1f2937" in type_badge("electric")
    assert "color:#ffffff" in type_badge("dragon")


def test_unknown_type_falls_back():
    assert FALLBACK_COLOR in type_badge("stellar")


def test_type_badges_joins_in_order():
    html = type_badges(["dragon", "ground"])
    assert html.index("Dragon") < html.index("Ground")


@pytest.mark.parametrize(
    "value, label",
    [(4, "4× ▲▲"), (2, "2× ▲"), (1, "1×"), (0.5, "½× ▼"), (0.25, "¼× ▼▼"), (0, "0× ✕"), (8, "8×")],
)
def test_format_multiplier(value, label):
    assert format_multiplier(value) == label


@pytest.mark.parametrize(
    "value, expected",
    [(4, "#b91c1c"), (2, "#f87171"), (0, "#60a5fa"), (0.5, "#86efac"), (1, "")],
)
def test_color_multiplier(value, expected):
    assert expected in color_multiplier(value)


@pytest.mark.parametrize(
    ("improvement", "expected"),
    [
        (2, "−2"),
        (0, "0"),
        (-2, "+2"),
        (1.5, "−1.5"),
        (-1.5, "+1.5"),
        (0.0, "0"),
        (-0.0, "0"),
    ],
)
def test_format_badness_change(improvement, expected):
    assert format_badness_change(improvement) == expected
