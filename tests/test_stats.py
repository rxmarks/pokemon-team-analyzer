from pokedex.analysis import stat_warnings


def make_stats(attack=100, special_attack=100, speed=80):
    return {
        "hp": 80,
        "attack": attack,
        "defense": 80,
        "special-attack": special_attack,
        "special-defense": 80,
        "speed": speed,
    }


def test_balanced_team_has_no_warnings():
    team = {"a": make_stats(attack=130, speed=110), "b": make_stats(special_attack=130)}
    assert stat_warnings(team) == []


def test_slow_team_flagged():
    team = {"a": make_stats(attack=130), "b": make_stats(special_attack=130)}
    assert any("fast" in w for w in stat_warnings(team))


def test_all_physical_team_flagged():
    team = {"a": make_stats(attack=130, speed=110), "b": make_stats(attack=120)}
    assert any("special attackers" in w for w in stat_warnings(team))


def test_speed_threshold_is_inclusive():
    team = {"a": make_stats(attack=130, speed=100), "b": make_stats(special_attack=130)}
    assert not any("fast" in w for w in stat_warnings(team))
