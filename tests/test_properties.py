from hypothesis import given, settings
from hypothesis import strategies as st

from pokedex.analysis import (
    coverage_gaps,
    member_coverage,
    member_profile,
    multiplier,
    score_team,
    suggest_swaps,
    team_badness,
    team_weak_total,
)
from pokedex.fetch import load_type_chart

CHART = load_type_chart()
TYPES = list(CHART)

types_st = st.sampled_from(TYPES)
typing_st = st.lists(types_st, min_size=1, max_size=2, unique=True)
team_st = st.dictionaries(
    keys=st.text(alphabet="abcdefghij", min_size=3, max_size=8),
    values=typing_st,
    min_size=1,
    max_size=6,
)


@given(types_st, typing_st)
def test_multiplier_is_valid_value(attack, defender):
    assert multiplier(attack, defender, CHART) in {0.0, 0.25, 0.5, 1.0, 2.0, 4.0}


@given(types_st, types_st, types_st)
def test_multiplier_ignores_type_order(attack, t1, t2):
    assert multiplier(attack, [t1, t2], CHART) == multiplier(attack, [t2, t1], CHART)


@given(typing_st)
def test_profile_covers_every_type(types):
    assert set(member_profile(types, CHART)) == set(TYPES)


@given(team_st)
def test_gaps_are_real_types(team):
    assert coverage_gaps(team, CHART) <= set(TYPES)


@given(team_st, typing_st)
def test_adding_member_never_adds_gaps(team, new_types):
    bigger = {**team, "zzznew": new_types}
    assert coverage_gaps(bigger, CHART) <= coverage_gaps(team, CHART)


@settings(max_examples=50)
@given(team_st)
def test_fast_scorer_matches_pandas_scorer(team):
    profiles = [member_profile(t, CHART) for t in team.values()]
    coverages = [member_coverage(t, CHART) for t in team.values()]
    badness, weak_total = score_team(profiles, coverages, TYPES)
    assert badness == team_badness(team, CHART)
    assert weak_total == team_weak_total(team, CHART)


@settings(max_examples=25, deadline=None)
@given(team_st, team_st)
def test_swap_improvement_is_consistent(team, candidates):
    df = suggest_swaps(team, candidates, CHART, top_n=5)
    assert len(df) <= 5
    base = team_badness(team, CHART)
    for row in df.itertuples():
        assert row.improvement == base - row.new_badness
        assert row.replaces in team
        assert row.candidate not in team
