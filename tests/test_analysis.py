import pytest

from pokedex.analysis import (
    MATCHUP_SWAP_COLUMNS,
    best_stab_multiplier,
    coverage_gaps,
    matchup_label,
    matchup_score,
    matchup_table,
    matchup_threat_pressure,
    member_coverage,
    member_profile,
    multiplier,
    opponent_threat_report,
    score_team,
    suggest_matchup_swaps,
    suggest_swaps,
    team_badness,
    team_matchup_balance,
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
    candidates = {
        "dragonite": ["dragon", "flying"],
        "scizor": ["bug", "steel"],
    }

    result = suggest_swaps(SAMPLE_TEAM, candidates, chart)

    assert "dragonite" not in set(result["candidate"])


def test_fast_score_matches_pandas_version(chart):
    profiles = [member_profile(types, chart) for types in SAMPLE_TEAM.values()]
    coverages = [member_coverage(types, chart) for types in SAMPLE_TEAM.values()]

    assert score_team(profiles, coverages, list(chart)) == (
        team_badness(SAMPLE_TEAM, chart),
        team_weak_total(SAMPLE_TEAM, chart),
    )


def test_best_stab_multiplier_uses_best_native_type(chart):
    assert best_stab_multiplier(["fire", "flying"], ["grass", "steel"], chart) == 4.0


def test_best_stab_multiplier_handles_immunity(chart):
    assert best_stab_multiplier(["normal"], ["ghost"], chart) == 0.0


def test_matchup_score_favors_water_into_fire(chart):
    assert matchup_score(["water"], ["fire"], chart) > 0


def test_matchup_score_is_risky_for_fire_into_water(chart):
    assert matchup_score(["fire"], ["water"], chart) < 0


def test_matchup_score_is_even_for_identical_types(chart):
    assert matchup_score(["water"], ["water"], chart) == 0.0


@pytest.mark.parametrize(
    "score, expected",
    [
        (1.0, "Favorable"),
        (0.0, "Even"),
        (-1.0, "Risky"),
    ],
)
def test_matchup_label(score, expected):
    assert matchup_label(score) == expected


def test_matchup_table_has_user_rows_and_opponent_columns(chart):
    team = {
        "squirtle": ["water"],
        "bulbasaur": ["grass"],
    }
    opponent = {
        "charmander": ["fire"],
        "pikachu": ["electric"],
    }

    table = matchup_table(team, opponent, chart)

    assert list(table.index) == ["squirtle", "bulbasaur"]
    assert list(table.columns) == ["charmander", "pikachu"]
    assert table.loc["squirtle", "charmander"] == "Favorable"
    assert table.loc["bulbasaur", "charmander"] == "Risky"
    assert table.loc["squirtle", "pikachu"] == "Risky"


def test_matchup_table_with_empty_opponent_team_has_team_rows(chart):
    team = {
        "squirtle": ["water"],
        "bulbasaur": ["grass"],
    }

    table = matchup_table(team, {}, chart)

    assert list(table.index) == ["squirtle", "bulbasaur"]
    assert table.empty


def test_opponent_threat_report_shows_answers(chart):
    team = {
        "squirtle": ["water"],
        "bulbasaur": ["grass"],
    }
    opponent = {
        "charmander": ["fire"],
    }

    report = opponent_threat_report(team, opponent, chart)

    assert list(report.columns) == [
        "opponent",
        "threatens",
        "answered_by",
        "threat_score",
        "weak_members",
        "answers",
    ]
    assert report.loc[0, "opponent"] == "charmander"
    assert report.loc[0, "threatens"] == 1
    assert report.loc[0, "answered_by"] == 1
    assert report.loc[0, "threat_score"] == 0
    assert report.loc[0, "weak_members"] == "bulbasaur"
    assert report.loc[0, "answers"] == "squirtle"


def test_opponent_threat_report_counts_electric_pressure_correctly(chart):
    team = {
        "dragonite": ["dragon", "flying"],
        "gyarados": ["water", "flying"],
        "bulbasaur": ["grass", "poison"],
    }
    opponent = {
        "charmander": ["fire"],
        "pikachu": ["electric"],
    }

    report = opponent_threat_report(team, opponent, chart)
    pikachu = report.loc[report["opponent"] == "pikachu"].iloc[0]

    assert pikachu["threatens"] == 1
    assert pikachu["weak_members"] == "gyarados"


def test_opponent_threat_report_with_empty_opponent_team_returns_empty_table(chart):
    team = {
        "squirtle": ["water"],
        "bulbasaur": ["grass"],
    }

    report = opponent_threat_report(team, {}, chart)

    assert report.empty
    assert list(report.columns) == [
        "opponent",
        "threatens",
        "answered_by",
        "threat_score",
        "weak_members",
        "answers",
    ]


def test_matchup_threat_pressure_sums_opponent_report(chart):
    team = {
        "charizard": ["fire", "flying"],
        "gyarados": ["water", "flying"],
    }
    opponents = {
        "pikachu": ["electric"],
    }

    assert matchup_threat_pressure(team, opponents, chart) == 2


def test_team_matchup_balance_favors_water_against_fire(chart):
    team = {
        "squirtle": ["water"],
    }
    opponents = {
        "charmander": ["fire"],
    }

    assert team_matchup_balance(team, opponents, chart) > 0


def test_matchup_swaps_empty_without_opponents(chart):
    team = {
        "squirtle": ["water"],
    }
    candidates = {
        "pikachu": ["electric"],
    }

    result = suggest_matchup_swaps(team, candidates, {}, chart)

    assert result.empty
    assert list(result.columns) == MATCHUP_SWAP_COLUMNS


def test_matchup_swaps_skip_existing_members(chart):
    team = {
        "squirtle": ["water"],
        "bulbasaur": ["grass"],
    }
    candidates = {
        "squirtle": ["water"],
        "pikachu": ["electric"],
    }
    opponents = {
        "charmander": ["fire"],
    }

    result = suggest_matchup_swaps(team, candidates, opponents, chart)

    assert "squirtle" not in set(result["candidate"])


def test_matchup_swaps_reduce_electric_pressure(chart):
    team = {
        "charizard": ["fire", "flying"],
        "gyarados": ["water", "flying"],
        "bulbasaur": ["grass", "poison"],
    }
    candidates = {
        "excadrill": ["ground", "steel"],
        "flareon": ["fire"],
    }
    opponents = {
        "pikachu": ["electric"],
    }

    result = suggest_matchup_swaps(team, candidates, opponents, chart)
    top = result.iloc[0]

    assert top["candidate"] == "excadrill"
    assert top["replaces"] in {"charizard", "gyarados"}
    assert top["pressure_improvement"] > 0
    assert top["threat_pressure"] < matchup_threat_pressure(team, opponents, chart)


def test_matchup_swap_ranking_is_deterministic(chart):
    team = {
        "squirtle": ["water"],
        "bulbasaur": ["grass"],
    }
    candidates = {
        "pikachu": ["electric"],
        "geodude": ["rock", "ground"],
    }
    opponents = {
        "charmander": ["fire"],
    }

    first = suggest_matchup_swaps(team, candidates, opponents, chart)
    second = suggest_matchup_swaps(team, candidates, opponents, chart)

    assert first.equals(second)


def test_matchup_swaps_equal_metrics_are_not_improvement(chart):
    team = {"z-original": ["water"]}
    candidates = {"a-alternative": ["water"]}
    opponents = {"charmander": ["fire"]}

    result = suggest_matchup_swaps(team, candidates, opponents, chart)
    row = result.iloc[0]

    assert not bool(row["is_improvement"])
    assert row["pressure_improvement"] == 0
    assert row["balance_improvement"] == 0
    assert row["badness_improvement"] == 0
    assert row["weakness_improvement"] == 0


def test_matchup_swaps_improvement_filter_excludes_equal_alternatives(chart):
    result = suggest_matchup_swaps(
        {"original": ["water"]},
        {"alternative": ["water"]},
        {"charmander": ["fire"]},
        chart,
        improvements_only=True,
    )

    assert result.empty
    assert list(result.columns) == MATCHUP_SWAP_COLUMNS


def test_matchup_swaps_improvement_filter_keeps_beneficial_swap(chart):
    result = suggest_matchup_swaps(
        {"charmander": ["fire"]},
        {"squirtle": ["water"]},
        {"opponent": ["water"]},
        chart,
        improvements_only=True,
    )

    assert len(result) == 1
    row = result.iloc[0]

    assert row["candidate"] == "squirtle"
    assert bool(row["is_improvement"])
    assert row["pressure_improvement"] > 0
    assert row["balance_improvement"] > 0


def test_matchup_swap_deltas_match_recomputed_scores(chart):
    team = {
        "charizard": ["fire", "flying"],
        "gyarados": ["water", "flying"],
    }
    candidates = {"excadrill": ["ground", "steel"]}
    opponents = {"pikachu": ["electric"]}

    result = suggest_matchup_swaps(team, candidates, opponents, chart)
    row = result.iloc[0]

    swapped_team = {
        name: candidates[row["candidate"]] if name == row["replaces"] else types
        for name, types in team.items()
    }

    assert row["pressure_improvement"] == (
        matchup_threat_pressure(team, opponents, chart)
        - matchup_threat_pressure(swapped_team, opponents, chart)
    )
    assert row["balance_improvement"] == pytest.approx(
        team_matchup_balance(swapped_team, opponents, chart)
        - team_matchup_balance(team, opponents, chart)
    )
    assert row["badness_improvement"] == (
        team_badness(team, chart) - team_badness(swapped_team, chart)
    )
    assert row["weakness_improvement"] == (
        team_weak_total(team, chart) - team_weak_total(swapped_team, chart)
    )


def test_matchup_swaps_worse_alternative_is_not_improvement(chart):
    team = {"squirtle": ["water"]}
    candidates = {"charmander": ["fire"]}
    opponents = {"opponent": ["water"]}

    result = suggest_matchup_swaps(team, candidates, opponents, chart)
    row = result.iloc[0]

    assert not bool(row["is_improvement"])
    assert row["pressure_improvement"] < 0

    filtered = suggest_matchup_swaps(
        team,
        candidates,
        opponents,
        chart,
        improvements_only=True,
    )

    assert filtered.empty
