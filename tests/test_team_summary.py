from copy import deepcopy

import pandas as pd

from pokedex.team_summary import (
    QuadWeakness,
    SharedWeakness,
    TeamSummary,
    summarize_team,
)


def sample_team():
    return {
        "member-a": ["fire"],
        "member-b": ["rock"],
        "member-c": ["grass"],
    }


def sample_table():
    return pd.DataFrame(
        {
            "member-a": [4.0, 2.0, 0.5],
            "member-b": [2.0, 1.0, 1.0],
            "member-c": [0.5, 2.0, 1.0],
            "# weak": [2, 2, 0],
            "# resist": [1, 0, 1],
            "total": [6.5, 5.0, 2.5],
        },
        index=["water", "ground", "fire"],
    )


def test_reports_shared_weaknesses_and_affected_members():
    summary = summarize_team(
        sample_team(),
        sample_table(),
        {"ice", "dragon"},
    )

    assert summary.shared_weaknesses == (
        SharedWeakness("ground", ("member-a", "member-c")),
        SharedWeakness("water", ("member-a", "member-b")),
    )


def test_reports_quad_weakness_member_type_pairs():
    summary = summarize_team(sample_team(), sample_table(), set())

    assert summary.quad_weaknesses == (QuadWeakness("member-a", "water"),)


def test_sorts_coverage_gaps():
    summary = summarize_team(
        sample_team(),
        sample_table(),
        {"ice", "dragon", "electric"},
    )

    assert summary.native_coverage_gaps == ("dragon", "electric", "ice")


def test_prioritizes_types_affecting_more_members():
    table = sample_table()
    table.loc["water", "member-c"] = 2.0

    summary = summarize_team(sample_team(), table, set())

    assert [weakness.attack_type for weakness in summary.shared_weaknesses] == [
        "water",
        "ground",
    ]
    assert summary.shared_weaknesses[0].members == (
        "member-a",
        "member-b",
        "member-c",
    )


def test_member_order_follows_team_order():
    team = {
        "member-c": ["grass"],
        "member-b": ["rock"],
        "member-a": ["fire"],
    }

    summary = summarize_team(team, sample_table(), set())

    assert summary.shared_weaknesses == (
        SharedWeakness("ground", ("member-c", "member-a")),
        SharedWeakness("water", ("member-b", "member-a")),
    )


def test_multiple_quad_weaknesses_are_separate_pairs():
    table = sample_table()
    table.loc["ground", "member-a"] = 4.0
    table.loc["ground", "member-c"] = 4.0

    summary = summarize_team(sample_team(), table, set())

    assert summary.quad_weaknesses == (
        QuadWeakness("member-a", "ground"),
        QuadWeakness("member-a", "water"),
        QuadWeakness("member-c", "ground"),
    )


def test_neutral_and_resisted_types_are_not_weaknesses():
    team = {"member-a": ["normal"]}
    table = pd.DataFrame(
        {"member-a": [0.0, 0.25, 0.5, 1.0]},
        index=["ghost", "grass", "fire", "water"],
    )

    assert summarize_team(team, table, set()) == TeamSummary()


def test_single_member_weakness_is_not_shared():
    team = {"member-a": ["fire"]}
    table = pd.DataFrame(
        {"member-a": [2.0]},
        index=["water"],
    )

    summary = summarize_team(team, table, set())

    assert summary.shared_weaknesses == ()
    assert summary.quad_weaknesses == ()


def test_empty_team_returns_empty_summary():
    assert summarize_team({}, pd.DataFrame(), set()) == TeamSummary()


def test_does_not_mutate_inputs():
    team = sample_team()
    table = sample_table()
    gaps = {"ice", "dragon"}

    before_team = deepcopy(team)
    before_table = table.copy(deep=True)
    before_gaps = set(gaps)

    summarize_team(team, table, gaps)

    assert team == before_team
    pd.testing.assert_frame_equal(table, before_table)
    assert gaps == before_gaps
