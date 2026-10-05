from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import pokedex.fetch as fetch
import pokedex.move_ui as move_ui

APP = str(Path(__file__).resolve().parent.parent / "app.py")

FAKE_TYPES = {
    "dragonite": ["dragon", "flying"],
    "gyarados": ["water", "flying"],
    "garchomp": ["dragon", "ground"],
    "ferrothorn": ["grass", "steel"],
    "togekiss": ["fairy", "flying"],
    "tyranitar": ["rock", "dark"],
}
FAKE_STATS = {
    "hp": 90,
    "attack": 120,
    "defense": 90,
    "special-attack": 80,
    "special-defense": 90,
    "speed": 100,
}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    st.cache_data.clear()
    monkeypatch.setattr(fetch, "get_all_pokemon_names", lambda: sorted(FAKE_TYPES))
    monkeypatch.setattr(fetch, "get_types", lambda name: FAKE_TYPES[name])
    monkeypatch.setattr(fetch, "get_stats", lambda name: FAKE_STATS)
    monkeypatch.setattr(move_ui, "get_learnable_moves", lambda name: ["earthquake", "ice-beam"])


def run_app():
    return AppTest.from_file(APP, default_timeout=60).run()


def run_app_with_team(team: str):
    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["team"] = team
    return at.run()


def test_app_loads_default_team():
    at = run_app()
    assert not at.exception
    headers = [h.value for h in at.subheader]
    assert "Defense: weakness table" in headers
    assert "Swap suggestions" in headers


def test_app_with_empty_team_shows_prompt():
    at = run_app()
    at.multiselect[0].set_value([]).run()
    assert not at.exception
    assert at.info[0].value == "Pick at least one Pokémon to start."


def test_url_loads_team():
    at = run_app_with_team("garchomp,tyranitar")
    assert not at.exception
    assert at.multiselect[0].value == ["garchomp", "tyranitar"]


def test_url_drops_invalid_and_duplicate_names():
    at = run_app_with_team("Garchomp, notreal,garchomp")
    assert not at.exception
    assert at.multiselect[0].value == ["garchomp"]


def test_url_with_only_invalid_names_falls_back_to_default():
    at = run_app_with_team("missingno")
    assert not at.exception
    assert at.multiselect[0].value == list(FAKE_TYPES)


PASTE = """\
Chompy (Garchomp) (M) @ Choice Scarf
- Earthquake

Tyranitar @ Leftovers
- Crunch

Pikachu @ Light Ball
- Thunderbolt
"""


def test_showdown_import_replaces_team():
    at = run_app()
    at.text_area(key="showdown_paste").input(PASTE)
    at.button(key="import_btn").click().run()
    assert not at.exception
    assert at.multiselect[0].value == ["garchomp", "tyranitar"]
    assert any("pikachu" in w.value for w in at.warning)


def test_showdown_import_with_no_valid_pokemon_keeps_team():
    at = run_app()
    at.text_area(key="showdown_paste").input("Missingno @ Nothing")
    at.button(key="import_btn").click().run()
    assert not at.exception
    assert at.multiselect[0].value == list(FAKE_TYPES)
    assert any("Couldn't find" in e.value for e in at.error)
