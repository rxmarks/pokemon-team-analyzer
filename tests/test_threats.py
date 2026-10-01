from pokedex.analysis import threat_report
from pokedex.fetch import load_type_chart

CHART = load_type_chart()


def test_weak_and_answer_counts():
    team = {"glalie": ["ice"]}
    report = threat_report(team, {"great-tusk": ["ground", "fighting"]}, CHART)
    assert report[0]["members_weak"] == 1
    assert report[0]["answers"] == 1
    assert report[0]["danger"] is False


def test_no_answers_is_danger():
    team = {"snorlax": ["normal"]}
    report = threat_report(team, {"kingambit": ["dark", "steel"]}, CHART)
    assert report[0]["answers"] == 0
    assert report[0]["danger"] is True


def test_three_weak_members_is_danger():
    team = {"a": ["fire"], "b": ["fire"], "c": ["fire"], "d": ["electric"]}
    report = threat_report(team, {"pelipper": ["water", "flying"]}, CHART)
    assert report[0]["members_weak"] == 3
    assert report[0]["answers"] == 1
    assert report[0]["danger"] is True
