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


def test_can_parse_roster_without_team_limit():
    paste = "\n\n".join(f"Pokemon-{index} @ Leftovers\n- Tackle" for index in range(8))

    roster = parse_showdown(paste, max_members=None)

    assert [mon.species for mon in roster] == [f"pokemon-{index}" for index in range(8)]


def test_explicit_member_limit():
    paste = "\n\n".join(f"Pokemon-{index}\n- Tackle" for index in range(4))

    assert len(parse_showdown(paste, max_members=2)) == 2
    assert parse_showdown(paste, max_members=0) == []


def test_rejects_negative_member_limit():
    with pytest.raises(ValueError, match="nonnegative"):
        parse_showdown("Garchomp", max_members=-1)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("Nidoran♀", "nidoran-f"),
        ("Nidoran♂", "nidoran-m"),
        ("Mimey (Mr. Mime) (M) @ Leftovers", "mr-mime"),
        ("RotomWash @ Leftovers", "rotom-wash"),
        ("TypeNull", "type-null"),
        ("Farfetch’d", "farfetchd"),
    ],
)
def test_species_aliases_are_resolved_in_headers(header, expected):
    parsed = parse_showdown(header + "\n- Swords Dance")

    assert len(parsed) == 1
    assert parsed[0].species == expected
    assert parsed[0].moves == ["swords-dance"]


def test_species_translation_does_not_change_move_normalization():
    parsed = parse_showdown("Nidoran♀\n- Hidden Power [Fire]\n- Will-O-Wisp\n")

    assert parsed[0].species == "nidoran-f"
    assert parsed[0].moves == ["hidden-power", "will-o-wisp"]
