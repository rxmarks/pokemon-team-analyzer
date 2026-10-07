import pytest

from pokedex.usage_context import usage_context


def test_context_interprets_recorded_dataset():
    context = usage_context("gen9ou-1695", "2026-09")

    assert context.dataset_id == "gen9ou-1695"
    assert context.month == "2026-09"
    assert context.weighting_baseline == 1695
    assert context.source_url == ("https://www.smogon.com/stats/2026-09/gen9ou-1695.txt.gz")


def test_zero_baseline_is_preserved():
    context = usage_context("gen9ou-0", "2026-09")

    assert context.weighting_baseline == 0


def test_missing_baseline_is_not_invented():
    context = usage_context("gen9ou", "2026-09")

    assert context.weighting_baseline is None
    assert context.source_url == ("https://www.smogon.com/stats/2026-09/gen9ou.txt.gz")


def test_context_strips_surrounding_whitespace():
    context = usage_context(" gen9ou-1695 ", " 2026-09 ")

    assert context.dataset_id == "gen9ou-1695"
    assert context.month == "2026-09"
    assert context.weighting_baseline == 1695


@pytest.mark.parametrize(
    "month",
    [None, "", "2026-13", "2026-00", "2026-9", "../2026-09"],
)
def test_invalid_or_missing_month_prevents_source_link(month):
    context = usage_context("gen9ou-1695", month)

    assert context.month is None
    assert context.source_url is None
    assert context.weighting_baseline == 1695


@pytest.mark.parametrize(
    "dataset",
    [None, "", "../gen9ou-1695", "gen9ou-1695?x=1"],
)
def test_invalid_or_missing_dataset_prevents_source_link(dataset):
    context = usage_context(dataset, "2026-09")

    assert context.dataset_id is None
    assert context.weighting_baseline is None
    assert context.source_url is None
    assert context.month == "2026-09"
