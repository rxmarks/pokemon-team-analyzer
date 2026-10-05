import json

import pytest
import requests

from pokedex import fetch


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


def fake_get(payload, status=200, calls=None):
    def _get(url, timeout):
        if calls is not None:
            calls.append(url)
        return FakeResponse(payload, status)

    return _get


def test_get_types_parses_and_cleans_name(monkeypatch):
    calls = []
    payload = {"types": [{"type": {"name": "dragon"}}, {"type": {"name": "flying"}}]}
    monkeypatch.setattr(fetch._session, "get", fake_get(payload, calls=calls))
    assert fetch.get_types("  Dragonite ") == ["dragon", "flying"]
    assert calls[0].endswith("/pokemon/dragonite")


def test_get_stats(monkeypatch):
    payload = {
        "stats": [
            {"stat": {"name": "hp"}, "base_stat": 91},
            {"stat": {"name": "speed"}, "base_stat": 80},
        ]
    }
    monkeypatch.setattr(fetch._session, "get", fake_get(payload))
    assert fetch.get_stats("dragonite") == {"hp": 91, "speed": 80}


def test_get_learnable_moves_sorted(monkeypatch):
    payload = {"moves": [{"move": {"name": "outrage"}}, {"move": {"name": "earthquake"}}]}
    monkeypatch.setattr(fetch._session, "get", fake_get(payload))
    assert fetch.get_learnable_moves("garchomp") == ["earthquake", "outrage"]


def test_get_all_pokemon_names_sorted(monkeypatch):
    payload = {"results": [{"name": "pikachu"}, {"name": "abra"}]}
    monkeypatch.setattr(fetch._session, "get", fake_get(payload))
    assert fetch.get_all_pokemon_names() == ["abra", "pikachu"]


def test_http_error_raises(monkeypatch):
    monkeypatch.setattr(fetch._session, "get", fake_get({}, status=404))
    with pytest.raises(requests.HTTPError):
        fetch.get_types("notapokemon")


def test_timeout_propagates(monkeypatch):
    def timeout_get(url, timeout):
        raise requests.Timeout("too slow")

    monkeypatch.setattr(fetch._session, "get", timeout_get)
    with pytest.raises(requests.RequestException):
        fetch.get_learnable_moves("garchomp")


def test_load_type_chart_downloads_then_reads_cache(monkeypatch, tmp_path):
    path = tmp_path / "types.json"
    monkeypatch.setattr(fetch, "DATA_PATH", path)
    payload = {
        "damage_relations": {
            "double_damage_from": [{"name": "fighting"}],
            "half_damage_from": [],
            "no_damage_from": [{"name": "ghost"}],
        }
    }
    monkeypatch.setattr(fetch._session, "get", fake_get(payload))

    chart = fetch.load_type_chart()
    assert len(chart) == 18
    assert chart["normal"]["no_damage_from"] == ["ghost"]
    assert path.exists()

    def no_network(url, timeout):
        raise AssertionError("should read the saved file, not call the API")

    monkeypatch.setattr(fetch._session, "get", no_network)
    assert fetch.load_type_chart() == chart


@pytest.mark.parametrize(
    "path_attr, loader",
    [
        ("POKEMON_CACHE_PATH", "load_pokemon_cache"),
        ("MOVES_CACHE_PATH", "load_move_cache"),
        ("SMOGON_PATH", "load_smogon_usage"),
    ],
)
def test_cache_loaders_read_json(monkeypatch, tmp_path, path_attr, loader):
    path = tmp_path / "data.json"
    path.write_text(json.dumps({"ok": True}), encoding="utf-8")
    monkeypatch.setattr(fetch, path_attr, path)
    assert getattr(fetch, loader)() == {"ok": True}


def test_session_retries_transient_errors():
    retry = fetch._session.get_adapter("https://pokeapi.co").max_retries
    assert retry.total == 3
    assert 503 in retry.status_forcelist
    assert 404 not in retry.status_forcelist


def test_get_sprite_returns_url(monkeypatch):
    payload = {"sprites": {"front_default": "https://example.com/garchomp.png"}}
    monkeypatch.setattr(fetch._session, "get", fake_get(payload))
    assert fetch.get_sprite("garchomp") == "https://example.com/garchomp.png"


def test_get_sprite_missing_returns_none(monkeypatch):
    payload = {"sprites": {"front_default": None}}
    monkeypatch.setattr(fetch._session, "get", fake_get(payload))
    assert fetch.get_sprite("some-form") is None


CACHE = {"garchomp": {"types": ["dragon", "ground"], "stats": {"hp": 108, "attack": 130}}}


def _no_api(*args, **kwargs):
    raise AssertionError("PokeAPI should not be called for cached names")


def test_types_cache_first_uses_cache(monkeypatch):
    monkeypatch.setattr(fetch, "get_types", _no_api)
    assert fetch.types_cache_first("garchomp", CACHE) == ["dragon", "ground"]


def test_types_cache_first_falls_back(monkeypatch):
    monkeypatch.setattr(fetch, "get_types", lambda name: ["fire"])
    assert fetch.types_cache_first("missingno", CACHE) == ["fire"]


def test_stats_cache_first_uses_cache(monkeypatch):
    monkeypatch.setattr(fetch, "get_stats", _no_api)
    assert fetch.stats_cache_first("garchomp", CACHE) == {"hp": 108, "attack": 130}


def test_stats_cache_first_falls_back(monkeypatch):
    monkeypatch.setattr(fetch, "get_stats", lambda name: {"hp": 1})
    assert fetch.stats_cache_first("missingno", CACHE) == {"hp": 1}


def test_cache_first_returns_copies():
    fetch.types_cache_first("garchomp", CACHE).append("fire")
    assert CACHE["garchomp"]["types"] == ["dragon", "ground"]
