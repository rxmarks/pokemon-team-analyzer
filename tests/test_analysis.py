import pytest

from pokedex.analysis import (
    coverage_gaps,
    member_coverage,
    member_profile,
    multiplier,
    score_team,
    suggest_swaps,
    team_badness,
    team_table,
    team_weak_total,
)
from pokedex.fetch import load_type_chart

SAMPLE_TEAM = {
    "dragonite": ["dragon", "flying"],
    "gyarados": ["water", "flying"],
    "garchomp": ["dragon", "ground"],
    "ferrothorn": ["grass", "steel"],
    "togekiss": ["fairy", "flying"],
    "tyranitar": ["rock", "dark"],
}


@pytest.fixture(scope="session")
def chart():
    return load_type_chart()


@pytest.mark.parametrize(
    "attack, defender, expected",
    [
        ("ice", ["dragon", "flying"], 4.0),
        ("ground", ["rock", "flying"], 0.0),
        ("electric", ["water", "flying"], 4.0),
        ("fire", ["grass", "steel"], 4.0),
        ("fighting", ["fairy", "flying"], 0.25),
        ("water", ["fire"], 2.0),
        ("normal", ["normal"], 1.0),
    ],
)
def test_multiplier(chart, attack, defender, expected):
    assert multiplier(attack, defender, chart) == expected


def test_multipliers_are_valid_values(chart):
    allowed = {0.0, 0.25, 0.5, 1.0, 2.0, 4.0}
    table = team_table(SAMPLE_TEAM, chart)
    assert set(table[list(SAMPLE_TEAM)].to_numpy().flatten()) <= allowed


def test_chart_has_18_types(chart):
    assert len(chart) == 18


def test_ice_is_biggest_weakness(chart):
    table = team_table(SAMPLE_TEAM, chart)
    assert table.index[0] == "ice"
    assert table.loc["ice", "# weak"] == 3
    assert table.loc["ice", "# resist"] == 0


def test_sample_team_coverage_gap_is_normal(chart):
    assert coverage_gaps(SAMPLE_TEAM, chart) == {"normal"}


def test_normal_only_team_covers_nothing(chart):
    gaps = coverage_gaps({"snorlax": ["normal"]}, chart)
    assert gaps == set(chart)


def test_sample_team_badness(chart):
    assert team_badness(SAMPLE_TEAM, chart) == 4


def test_top_swap_is_scizor_for_dragonite(chart):
    candidates = {
        "scizor": ["bug", "steel"],
        "gengar": ["ghost", "poison"],
        "breloom": ["grass", "fighting"],
    }
    top = suggest_swaps(SAMPLE_TEAM, candidates, chart).iloc[0]
    assert top["candidate"] == "scizor"
    assert top["replaces"] == "dragonite"


def test_swaps_skip_existing_members(chart):
    candidates = {"dragonite": ["dragon", "flying"], "scizor": ["bug", "steel"]}
    result = suggest_swaps(SAMPLE_TEAM, candidates, chart)
    assert "dragonite" not in set(result["candidate"])


def test_fast_score_matches_pandas_version(chart):
    profiles = [member_profile(t, chart) for t in SAMPLE_TEAM.values()]
    coverages = [member_coverage(t, chart) for t in SAMPLE_TEAM.values()]
    assert score_team(profiles, coverages, list(chart)) == (
        team_badness(SAMPLE_TEAM, chart),
        team_weak_total(SAMPLE_TEAM, chart),
    )
