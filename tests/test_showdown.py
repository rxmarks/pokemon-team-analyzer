import pytest

from pokedex.showdown import normalize, parse_showdown

SAMPLE = """\
Chompy (Garchomp) (M) @ Choice Scarf
Ability: Rough Skin
EVs: 252 Atk / 4 SpD / 252 Spe
Jolly Nature
- Earthquake
- Outrage
- Stone Edge
- Fire Fang

Tyranitar @ Leftovers
Ability: Sand Stream
- Stealth Rock
- Knock Off
- Hidden Power [Fire]
- Crunch
- Extra Move

Iron Valiant (F)
- Moonblast
"""


def test_parses_species_from_all_header_styles():
    assert [m.species for m in parse_showdown(SAMPLE)] == [
        "garchomp",
        "tyranitar",
        "iron-valiant",
    ]


def test_parses_moves_and_caps_at_four():
    team = parse_showdown(SAMPLE)
    assert team[0].moves == ["earthquake", "outrage", "stone-edge", "fire-fang"]
    assert team[1].moves == ["stealth-rock", "knock-off", "hidden-power", "crunch"]


def test_limits_team_to_six():
    paste = "\n\n".join("Pikachu @ Light Ball\n- Thunderbolt" for _ in range(8))
    assert len(parse_showdown(paste)) == 6


def test_skips_teambuilder_headers_and_handles_windows_newlines():
    paste = "=== [gen9ou] Sand ===\r\n\r\nGarchomp @ Life Orb\r\n- Earthquake\r\n"
    assert [m.species for m in parse_showdown(paste)] == ["garchomp"]


def test_empty_paste_returns_empty_team():
    assert parse_showdown("   \n\n  ") == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Mr. Mime", "mr-mime"),
        ("Farfetch’d", "farfetchd"),
        ("Flabébé", "flabebe"),
        ("Type: Null", "type-null"),
        ("Porygon-Z", "porygon-z"),
        ("  Great   Tusk ", "great-tusk"),
    ],
)
def test_normalize(raw, expected):
    assert normalize(raw) == expected
