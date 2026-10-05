from pokedex import fetch


class FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {
            "results": [
                {"name": "zubat"},
                {"name": "abra"},
                {"name": "rotom-wash"},
            ]
        }


def test_get_all_pokemon_names_returns_sorted_names(monkeypatch):
    monkeypatch.setattr(fetch._session, "get", lambda *args, **kwargs: FakeResponse())

    assert fetch.get_all_pokemon_names() == [
        "abra",
        "rotom-wash",
        "zubat",
    ]


class FakeStatsResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {
            "stats": [
                {"stat": {"name": "hp"}, "base_stat": 91},
                {"stat": {"name": "speed"}, "base_stat": 80},
            ]
        }


def test_get_stats_parses_names(monkeypatch):
    monkeypatch.setattr(fetch._session, "get", lambda *args, **kwargs: FakeStatsResponse())
    assert fetch.get_stats("dragonite") == {"hp": 91, "speed": 80}
