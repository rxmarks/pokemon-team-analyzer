from streamlit.testing.v1 import AppTest


def test_summary_labels_partial_analysis():
    at = AppTest.from_string(
        """
from pokedex.team_summary import TeamSummary
from pokedex.team_summary_ui import render_team_summary

render_team_summary(
    TeamSummary(),
    selected_count=3,
    analyzed_count=2,
)
"""
    ).run()

    assert not at.exception
    assert any(
        warning.value.startswith("Partial analysis: loaded 2 of 3 selected Pokémon.")
        for warning in at.warning
    )


def test_summary_reports_truncated_lists():
    at = AppTest.from_string(
        """
from pokedex.team_summary import QuadWeakness, SharedWeakness, TeamSummary
from pokedex.team_summary_ui import render_team_summary

summary = TeamSummary(
    shared_weaknesses=tuple(
        SharedWeakness(attack_type, ("garchomp", "tyranitar"))
        for attack_type in ("fairy", "ground", "ice", "water")
    ),
    quad_weaknesses=tuple(
        QuadWeakness("garchomp", attack_type)
        for attack_type in ("ice", "fire", "water", "grass")
    ),
    native_coverage_gaps=("dragon",),
)

render_team_summary(
    summary,
    selected_count=2,
    analyzed_count=2,
)
"""
    ).run()

    assert not at.exception
    assert any("plus 1 other attack type" in element.value for element in at.markdown)
    assert any("plus 1 other member/type pair" in element.value for element in at.markdown)


def test_summary_avoids_overall_rating_for_clean_checks():
    at = AppTest.from_string(
        """
from pokedex.team_summary import TeamSummary
from pokedex.team_summary_ui import render_team_summary

render_team_summary(
    TeamSummary(),
    selected_count=1,
    analyzed_count=1,
)
"""
    ).run()

    assert not at.exception
    assert not at.warning
    assert any("This does not verify which moves" in element.value for element in at.markdown)
    assert not at.success
