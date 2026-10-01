from pokedex import fetch


class FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {"results": [{"name": "zubat"}, {"name": "abra"}, {"name": "rotom-wash"}]}


def test_get_all_pokemon_names_returns_sorted_names(monkeypatch):
    monkeypatch.setattr(fetch.requests, "get", lambda *args, **kwargs: FakeResponse())
    assert fetch.get_all_pokemon_names() == ["abra", "rotom-wash", "zubat"]