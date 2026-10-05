from hypothesis import given
from hypothesis import strategies as st

from pokedex.loadout import loadout_coverage, suggest_loadouts, usable_moves

CHART = {
    "ground": {"double_damage_to": ["fire", "electric", "steel"]},
    "dragon": {"double_damage_to": ["dragon"]},
    "ice": {"double_damage_to": ["dragon", "flying"]},
    "fire": {"double_damage_to": ["steel", "ice"]},
    "normal": {"double_damage_to": []},
}
MOVES = {
    "earthquake": {"type": "ground", "damage_class": "physical", "power": 100},
    "bulldoze": {"type": "ground", "damage_class": "physical", "power": 60},
    "dragon-claw": {"type": "dragon", "damage_class": "physical", "power": 80},
    "ice-fang": {"type": "ice", "damage_class": "physical", "power": 65},
    "fire-fang": {"type": "fire", "damage_class": "physical", "power": 65},
    "swords-dance": {"type": "normal", "damage_class": "status", "power": None},
    "hyper-beam": {"type": "normal", "damage_class": "special", "power": 150},
    "tackle": {"type": "normal", "damage_class": "physical", "power": 40},
}
TEAM = {"garchomp": ["dragon", "ground"]}
STATS = {"garchomp": {"attack": 130, "special-attack": 80}}
LEARN = {"garchomp": list(MOVES)}


def test_filters_status_weak_and_blocklisted():
    assert set(usable_moves(list(MOVES), MOVES)) == {
        "earthquake",
        "bulldoze",
        "dragon-claw",
        "ice-fang",
        "fire-fang",
    }


def test_starts_with_stab_and_avoids_duplicate_types():
    picks = suggest_loadouts(TEAM, LEARN, STATS, MOVES, CHART)["garchomp"]
    assert MOVES[picks[0]]["type"] in TEAM["garchomp"]
    assert len({MOVES[m]["type"] for m in picks}) == len(picks)
    assert "bulldoze" not in picks


def test_covers_reachable_types():
    loadouts = suggest_loadouts(TEAM, LEARN, STATS, MOVES, CHART)
    assert {"flying", "ice", "steel"} <= loadout_coverage(loadouts, MOVES, CHART)


def test_empty_learnset_returns_empty():
    assert suggest_loadouts(TEAM, {"garchomp": []}, STATS, MOVES, CHART) == {"garchomp": []}


@given(st.lists(st.sampled_from(list(MOVES)), unique=True))
def test_at_most_four_learnable_moves(learnable):
    picks = suggest_loadouts(TEAM, {"garchomp": learnable}, STATS, MOVES, CHART)["garchomp"]
    assert len(picks) <= 4
    assert set(picks) <= set(learnable)
