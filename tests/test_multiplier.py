import pytest

from pokedex.analysis import multiplier
from pokedex.fetch import load_type_chart

CHART = load_type_chart()


@pytest.mark.parametrize(
    ("attack", "defender", "expected"),
    [
        ("fire", ["grass"], 2.0),
        ("water", ["fire", "rock"], 4.0),
        ("ground", ["flying"], 0.0),
        ("normal", ["ghost"], 0.0),
        ("electric", ["water", "flying"], 4.0),
        ("fire", ["water", "dragon"], 0.25),
        ("fighting", ["normal", "ghost"], 0.0),
        ("ice", ["dragon", "ground"], 4.0),
        ("grass", ["water", "ground"], 4.0),
        ("fire", ["fire"], 0.5),
        ("normal", ["normal"], 1.0),
    ],
)
def test_multiplier_known_matchups(attack, defender, expected):
    assert multiplier(attack, defender, CHART) == expected
