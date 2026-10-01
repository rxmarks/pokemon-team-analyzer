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