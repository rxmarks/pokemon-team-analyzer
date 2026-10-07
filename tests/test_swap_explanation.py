from copy import deepcopy

import pandas as pd
import pytest

from pokedex.swap_explanation import (
    SwapExplanation,
    WeaknessChange,
    compare_type_analysis,
)
from pokedex.team_summary import QuadWeakness


def comparison_inputs():
    return {
        "current_team": {
            "member-a": ["fire"],
            "member-b": ["grass"],
        },
        "proposed_team": {
            "member-c": ["water"],
            "member-b": ["grass"],
        },
        "current_table": pd.DataFrame(
            {
                "member-a": [4.0, 1.0, 1.0],
                "member-b": [2.0, 2.0, 1.0],
            },
            index=["ice", "fire", "ground"],
        ),
        "proposed_table": pd.DataFrame(
            {
                "member-c": [1.0, 4.0, 1.0],
                "member-b": [2.0, 2.0, 1.0],
            },
            index=["ice", "fire", "ground"],
        ),
        "current_gaps": {"normal", "dragon"},
        "proposed_gaps": {"normal", "electric"},
    }


def test_reports_shared_weakness_improvements_and_tradeoffs():
    explanation = compare_type_analysis(**comparison_inputs())

    assert explanation.reduced_shared_weaknesses == (
        WeaknessChange(
            "ice",
            ("member-a", "member-b"),
            ("member-b",),
        ),
    )
    assert explanation.increased_shared_weaknesses == (
        WeaknessChange(
            "fire",
            ("member-b",),
            ("member-c", "member-b"),
        ),
    )


def test_reports_removed_and_added_quad_pairs():
    explanation = compare_type_analysis(**comparison_inputs())

    assert explanation.removed_quad_weaknesses == (QuadWeakness("member-a", "ice"),)
    assert explanation.added_quad_weaknesses == (QuadWeakness("member-c", "fire"),)


def test_reports_closed_and_opened_native_gaps():
    explanation = compare_type_analysis(**comparison_inputs())

    assert explanation.closed_native_gaps == ("dragon",)
    assert explanation.opened_native_gaps == ("electric",)


def test_identical_analysis_has_no_changes():
    inputs = comparison_inputs()

    inputs["proposed_team"] = deepcopy(inputs["current_team"])
    inputs["proposed_table"] = inputs["current_table"].copy(deep=True)
    inputs["proposed_gaps"] = set(inputs["current_gaps"])

    assert compare_type_analysis(**inputs) == SwapExplanation()


def test_equal_weak_member_counts_are_not_improvements():
    inputs = comparison_inputs()
    inputs["proposed_table"].loc["ice", "member-c"] = 2.0

    explanation = compare_type_analysis(**inputs)

    assert explanation.reduced_shared_weaknesses == ()
    assert all(change.attack_type != "ice" for change in explanation.increased_shared_weaknesses)


def test_single_member_changes_are_not_shared_weakness_changes():
    inputs = comparison_inputs()
    inputs["current_table"].loc["ground", "member-a"] = 2.0

    explanation = compare_type_analysis(**inputs)

    assert all(change.attack_type != "ground" for change in explanation.reduced_shared_weaknesses)


def test_output_order_is_independent_of_table_row_order():
    inputs = comparison_inputs()
    inputs["current_table"].loc["ground"] = [2.0, 2.0]
    inputs["proposed_table"].loc["ground"] = [1.0, 1.0]
    inputs["current_gaps"] = {"normal", "dragon", "ice"}
    inputs["proposed_gaps"] = {"normal"}

    expected = compare_type_analysis(**inputs)

    inputs["current_table"] = inputs["current_table"].iloc[::-1]
    inputs["proposed_table"] = inputs["proposed_table"].iloc[::-1]

    actual = compare_type_analysis(**inputs)

    assert actual == expected
    assert [change.attack_type for change in actual.reduced_shared_weaknesses] == ["ground", "ice"]
    assert actual.closed_native_gaps == ("dragon", "ice")


def test_rejects_mismatched_attack_type_tables():
    inputs = comparison_inputs()
    inputs["proposed_table"] = inputs["proposed_table"].drop(index="ground")

    with pytest.raises(ValueError, match="same attack types"):
        compare_type_analysis(**inputs)


def test_does_not_mutate_inputs():
    inputs = comparison_inputs()
    before = deepcopy(inputs)

    compare_type_analysis(**inputs)

    assert inputs["current_team"] == before["current_team"]
    assert inputs["proposed_team"] == before["proposed_team"]
    assert inputs["current_gaps"] == before["current_gaps"]
    assert inputs["proposed_gaps"] == before["proposed_gaps"]
    pd.testing.assert_frame_equal(
        inputs["current_table"],
        before["current_table"],
    )
    pd.testing.assert_frame_equal(
        inputs["proposed_table"],
        before["proposed_table"],
    )
