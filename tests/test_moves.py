from pokedex.analysis import damaging_move_types

FAKE_CACHE = {
    "fire-fang": {"type": "fire", "damage_class": "physical", "power": 65},
    "earthquake": {"type": "ground", "damage_class": "physical", "power": 100},
    "swords-dance": {"type": "normal", "damage_class": "status", "power": None},
    "flamethrower": {"type": "fire", "damage_class": "special", "power": 90},
}


def test_collects_damaging_types():
    assert damaging_move_types(["fire-fang", "earthquake"], FAKE_CACHE) == {"fire", "ground"}


def test_skips_status_moves():
    assert damaging_move_types(["swords-dance"], FAKE_CACHE) == set()


def test_duplicate_types_collapse():
    assert damaging_move_types(["fire-fang", "flamethrower"], FAKE_CACHE) == {"fire"}


def test_unknown_move_ignored():
    assert damaging_move_types(["not-a-move", "earthquake"], FAKE_CACHE) == {"ground"}

from pokedex.analysis import gaps_from_attack_types, move_coverage_gaps

FAKE_CHART = {
    "fire": {"double_damage_to": ["grass"]},
    "grass": {"double_damage_to": ["ground"]},
    "ground": {"double_damage_to": ["fire"]},
    "normal": {"double_damage_to": []},
}


def test_gaps_from_attack_types():
    assert gaps_from_attack_types({"fire"}, FAKE_CHART) == {"fire", "ground", "normal"}


def test_no_attack_types_means_everything_is_a_gap():
    assert gaps_from_attack_types(set(), FAKE_CHART) == set(FAKE_CHART)


def test_move_coverage_uses_move_types_not_pokemon_types():
    team_moves = {"garchomp": ["earthquake", "fire-fang"]}
    assert move_coverage_gaps(team_moves, FAKE_CACHE, FAKE_CHART) == {"ground", "normal"}


def test_status_moves_add_no_coverage():
    team_moves = {"garchomp": ["swords-dance"]}
    assert move_coverage_gaps(team_moves, FAKE_CACHE, FAKE_CHART) == set(FAKE_CHART)