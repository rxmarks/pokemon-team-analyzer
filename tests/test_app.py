from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

import pokedex.analysis as analysis
import pokedex.fetch as fetch
import pokedex.loadout_ui as loadout_ui
import pokedex.move_ui as move_ui
from pokedex import threat_ui
from pokedex.showdown import parse_showdown
from pokedex.team_files import dump_team, load_team
from pokedex.team_state import TeamMember, TeamState
from pokedex.workspace_files import (
    WorkspaceState,
    dump_workspace,
    load_workspace,
)

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
    monkeypatch.setattr(
        move_ui,
        "get_learnable_moves",
        lambda name: ["earthquake", "ice-beam"],
    )
    monkeypatch.setattr(fetch, "get_sprite", lambda name: None)
    monkeypatch.setattr(
        threat_ui,
        "cached_pokemon",
        lambda: {
            name: {
                "types": types,
                "stats": FAKE_STATS,
            }
            for name, types in FAKE_TYPES.items()
        },
    )


def run_app():
    return AppTest.from_file(APP, default_timeout=60).run()


def run_app_with_team(team: str):
    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["team"] = team
    return at.run()


def test_app_loads_default_team():
    at = run_app()

    assert not at.exception
    headers = [header.value for header in at.subheader]
    assert "Team" in headers

    tabs = [tab.label for tab in at.tabs]
    assert tabs == [
        "Defense",
        "Offense",
        "Moves",
        "Opponent matchups",
        "Meta threats",
        "Stats",
        "Swaps",
    ]


def test_summary_metrics_render():
    at = run_app()

    assert not at.exception
    assert [metric.label for metric in at.metric][:5] == [
        "Team badness",
        "Shared weaknesses",
        "Coverage gaps",
        "4x weaknesses",
        "Best swap",
    ]


def test_loadout_section_renders():
    at = run_app()

    assert not at.exception
    assert "Suggested move loadouts" in [header.value for header in at.subheader]


def test_app_with_empty_team_shows_prompt():
    at = run_app()

    at.multiselect(key="team").set_value([]).run()

    assert not at.exception
    assert at.info[0].value == "Pick at least one Pokémon to start."


def test_url_loads_team():
    at = run_app_with_team("garchomp,tyranitar")

    assert not at.exception
    assert at.multiselect(key="team").value == ["garchomp", "tyranitar"]


def test_url_drops_invalid_and_duplicate_names():
    at = run_app_with_team("Garchomp, notreal,garchomp")

    assert not at.exception
    assert at.multiselect(key="team").value == ["garchomp"]


def test_url_with_only_invalid_names_falls_back_to_default():
    at = run_app_with_team("missingno")

    assert not at.exception
    assert at.multiselect(key="team").value == list(FAKE_TYPES)


def test_apply_swap_replaces_one_member():
    at = run_app_with_team("garchomp,tyranitar")

    assert not at.exception

    swap_buttons = [button for button in at.button if button.key and button.key.startswith("swap_")]
    if not swap_buttons:
        pytest.skip("No improving swap for this fake team")

    before = list(at.multiselect(key="team").value)

    swap_buttons[0].click().run()
    assert not at.exception
    at.button(key="confirm_swap_preview").click().run()
    after = list(at.multiselect(key="team").value)

    assert not at.exception
    assert len(after) == len(before)
    assert len(set(before) - set(after)) == 1
    assert at.query_params["team"] == [",".join(after)] or at.query_params["team"] == ",".join(
        after
    )


def test_offline_name_list_falls_back_to_cache(monkeypatch):
    def down():
        raise requests.ConnectionError("PokeAPI down")

    monkeypatch.setattr(fetch, "get_all_pokemon_names", down)

    at = run_app()

    assert not at.exception
    assert any("PokeAPI is unreachable" in warning.value for warning in at.warning)

    team_picker = at.multiselect(key="team")
    assert team_picker.options == sorted(FAKE_TYPES) or len(team_picker.options) == len(FAKE_TYPES)


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
    assert at.multiselect(key="team").value == ["garchomp", "tyranitar"]
    assert any("pikachu" in warning.value for warning in at.warning)


def test_showdown_import_with_no_valid_pokemon_keeps_team():
    at = run_app()

    at.text_area(key="showdown_paste").input("Missingno @ Nothing")
    at.button(key="import_btn").click().run()

    assert not at.exception
    assert at.multiselect(key="team").value == list(FAKE_TYPES)
    assert any("Couldn't find" in error.value for error in at.error)


def test_opponent_matchups_prompt_when_no_opponent_selected():
    at = run_app()

    assert not at.exception
    assert at.multiselect(key="opponent_team").value == []

    assert any(
        "Pick at least one opposing Pokémon to analyze matchups." in info.value for info in at.info
    )


def test_opponent_matchup_selector_accepts_pokemon():
    at = run_app()

    opponent_picker = at.multiselect(key="opponent_team")
    opponent_picker.set_value(["tyranitar"]).run()

    assert not at.exception
    assert at.multiselect(key="opponent_team").value == ["tyranitar"]


def test_opponent_matchup_results_render_for_selected_opponent():
    at = run_app()

    at.multiselect(key="opponent_team").set_value(["tyranitar"]).run()

    assert not at.exception
    assert "Opponent Matchups" in [header.value for header in at.subheader]

    rendered_dataframes = list(at.dataframe)
    assert len(rendered_dataframes) >= 3


def test_opponent_selection_allows_multiple_pokemon():
    at = run_app()

    opponents = ["dragonite", "ferrothorn", "tyranitar"]
    at.multiselect(key="opponent_team").set_value(opponents).run()

    assert not at.exception
    assert at.multiselect(key="opponent_team").value == opponents


def test_opponent_picker_uses_same_available_pokemon_as_team_picker():
    at = run_app()

    team_options = list(at.multiselect(key="team").options)
    opponent_options = list(at.multiselect(key="opponent_team").options)

    assert opponent_options == team_options


def test_matchup_swap_results_render():
    at = run_app_with_team("garchomp,tyranitar")
    at.multiselect(key="opponent_team").set_value(["ferrothorn"]).run()
    at.checkbox(key="matchup_improvements_only").uncheck().run()

    assert not at.exception

    tables = [element.value for element in at.dataframe]
    swap_tables = [
        table
        for table in tables
        if {"candidate", "replaces", "pressure_improvement"}.issubset(table.columns)
    ]

    assert len(swap_tables) == 1

    swaps = swap_tables[0]
    assert not swaps.empty
    assert "threat_pressure" in swaps.columns
    assert "matchup_balance" in swaps.columns
    assert not set(swaps["candidate"]) & {"garchomp", "tyranitar"}
    assert set(swaps["replaces"]) <= {"garchomp", "tyranitar"}


def test_matchup_swap_results_absent_without_opponents():
    at = run_app()

    assert not at.exception
    assert not any(
        {"candidate", "replaces", "pressure_improvement"}.issubset(element.value.columns)
        for element in at.dataframe
    )
    assert not any(button.key and button.key.startswith("matchup_swap_") for button in at.button)


def test_matchup_swap_button_updates_team_and_preserves_opponents():
    at = run_app_with_team("garchomp,tyranitar")
    opponents = ["ferrothorn"]

    at.multiselect(key="opponent_team").set_value(opponents).run()
    assert not at.exception

    at.checkbox(key="matchup_improvements_only").uncheck().run()
    assert not at.exception

    swap_table = next(
        element.value
        for element in at.dataframe
        if {"candidate", "replaces", "pressure_improvement"}.issubset(element.value.columns)
    )
    assert not swap_table.empty

    top = swap_table.iloc[0]
    before = list(at.multiselect(key="team").value)
    expected = [top["candidate"] if name == top["replaces"] else name for name in before]

    at.button(key="matchup_swap_0").click().run()
    assert not at.exception
    at.button(key="confirm_swap_preview").click().run()
    assert not at.exception
    assert at.multiselect(key="team").value == expected
    assert at.multiselect(key="opponent_team").value == opponents
    assert at.checkbox(key="matchup_improvements_only").value is False

    url_team = at.query_params["team"]
    assert url_team == ",".join(expected) or url_team == [",".join(expected)]


def test_matchup_swaps_show_prompt_when_no_candidates_are_eligible():
    at = run_app()

    at.multiselect(key="opponent_team").set_value(["tyranitar"]).run()

    assert not at.exception
    assert any(info.value == "No eligible single swaps are available." for info in at.info)
    assert not any(button.key and button.key.startswith("matchup_swap_") for button in at.button)


def test_matchup_improvement_filter_defaults_to_enabled():
    at = run_app_with_team("garchomp,tyranitar")
    at.multiselect(key="opponent_team").set_value(["ferrothorn"]).run()

    assert not at.exception
    assert at.checkbox(key="matchup_improvements_only").value is True

    swap_tables = [
        element.value
        for element in at.dataframe
        if {"candidate", "is_improvement"}.issubset(element.value.columns)
    ]

    for table in swap_tables:
        assert table["is_improvement"].all()


def test_matchup_swap_explanations_render():
    at = run_app_with_team("garchomp,tyranitar")
    at.multiselect(key="opponent_team").set_value(["ferrothorn"]).run()
    at.checkbox(key="matchup_improvements_only").uncheck().run()

    assert not at.exception
    assert any(expander.label.startswith("Why this swap?") for expander in at.expander)

    explanation_tables = [
        element.value
        for element in at.dataframe
        if {"Opponent", "Threatened before", "Threatened after"}.issubset(element.value.columns)
    ]

    assert explanation_tables
    assert explanation_tables[0]["Opponent"].tolist() == ["Ferrothorn"]


def apply_first_matchup_swap(at):
    """Preview and apply a targeted swap using the offline fixture."""
    at.multiselect(key="opponent_team").set_value(["ferrothorn"]).run()
    assert not at.exception

    at.checkbox(key="matchup_improvements_only").uncheck().run()
    assert not at.exception

    at.button(key="matchup_swap_0").click().run()
    assert not at.exception

    at.button(key="confirm_swap_preview").click().run()
    assert not at.exception

    return at


def test_undo_swap_restores_team_and_url():
    at = run_app_with_team("garchomp,tyranitar")
    before = list(at.multiselect(key="team").value)

    at = apply_first_matchup_swap(at)
    assert at.multiselect(key="team").value != before

    at.button(key="undo_swap").click().run()

    assert not at.exception
    assert at.multiselect(key="team").value == before
    assert at.multiselect(key="opponent_team").value == ["ferrothorn"]
    assert not any(button.key == "undo_swap" for button in at.button)

    url_team = at.query_params["team"]
    assert url_team == ",".join(before) or url_team == [",".join(before)]


def test_manual_team_edit_clears_undo():
    at = run_app_with_team("garchomp,tyranitar")
    at = apply_first_matchup_swap(at)

    assert any(button.key == "undo_swap" for button in at.button)

    at.multiselect(key="team").set_value(["dragonite"]).run()

    assert not at.exception
    assert at.multiselect(key="team").value == ["dragonite"]
    assert not any(button.key == "undo_swap" for button in at.button)


def test_successful_import_clears_undo():
    at = run_app_with_team("garchomp,tyranitar")
    at = apply_first_matchup_swap(at)

    at.text_area(key="showdown_paste").input(PASTE)
    at.button(key="import_btn").click().run()

    assert not at.exception
    assert at.multiselect(key="team").value == ["garchomp", "tyranitar"]
    assert not any(button.key == "undo_swap" for button in at.button)


def test_failed_import_preserves_undo():
    at = run_app_with_team("garchomp,tyranitar")
    at = apply_first_matchup_swap(at)
    swapped_team = list(at.multiselect(key="team").value)

    at.text_area(key="showdown_paste").input("Missingno @ Nothing")
    at.button(key="import_btn").click().run()

    assert not at.exception
    assert at.multiselect(key="team").value == swapped_team
    assert any(button.key == "undo_swap" for button in at.button)


def test_swap_preview_does_not_change_team_or_url():
    at = run_app_with_team("garchomp,tyranitar")
    before = list(at.multiselect(key="team").value)
    before_url = at.query_params["team"]

    at.multiselect(key="opponent_team").set_value(["ferrothorn"]).run()
    at.checkbox(key="matchup_improvements_only").uncheck().run()
    at.button(key="matchup_swap_0").click().run()

    assert not at.exception
    assert at.multiselect(key="team").value == before
    assert at.query_params["team"] == before_url
    assert "Swap preview" in [header.value for header in at.subheader]
    assert any(button.key == "confirm_swap_preview" for button in at.button)


def test_cancel_preview_preserves_team():
    at = run_app_with_team("garchomp,tyranitar")
    before = list(at.multiselect(key="team").value)

    at.multiselect(key="opponent_team").set_value(["ferrothorn"]).run()
    at.checkbox(key="matchup_improvements_only").uncheck().run()
    at.button(key="matchup_swap_0").click().run()
    at.button(key="cancel_swap_preview").click().run()

    assert not at.exception
    assert at.multiselect(key="team").value == before
    assert not any(button.key == "confirm_swap_preview" for button in at.button)
    assert not any(button.key == "undo_swap" for button in at.button)


def test_manual_team_edit_clears_preview():
    at = run_app_with_team("garchomp,tyranitar")

    at.multiselect(key="opponent_team").set_value(["ferrothorn"]).run()
    at.checkbox(key="matchup_improvements_only").uncheck().run()
    at.button(key="matchup_swap_0").click().run()

    assert not at.exception
    assert any(button.key == "confirm_swap_preview" for button in at.button)

    at.multiselect(key="team").set_value(["dragonite"]).run()

    assert not at.exception
    assert at.multiselect(key="team").value == ["dragonite"]
    assert not any(button.key == "confirm_swap_preview" for button in at.button)


def test_showdown_import_preserves_selected_moves():
    at = run_app()

    at.text_area(key="showdown_paste").input(PASTE)
    at.button(key="import_btn").click().run()

    assert not at.exception
    assert at.multiselect(key="moves_garchomp").value == ["earthquake"]
    assert at.multiselect(key="moves_tyranitar").value == ["crunch"]
    assert any("Crunch" in warning.value and "preserved" in warning.value for warning in at.warning)


def test_status_moves_can_be_selected(monkeypatch):
    monkeypatch.setattr(
        move_ui,
        "cached_learnable_moves",
        lambda name: ["earthquake", "swords-dance"],
    )
    monkeypatch.setattr(
        move_ui,
        "cached_move_cache",
        lambda: {
            "earthquake": {"type": "ground", "damage_class": "physical"},
            "swords-dance": {"type": "normal", "damage_class": "status"},
        },
    )

    at = run_app_with_team("garchomp")
    at.multiselect(key="moves_garchomp").set_value(["swords-dance"]).run()

    assert not at.exception
    assert at.multiselect(key="moves_garchomp").value == ["swords-dance"]
    info_messages = [info.value for info in at.info]
    warning_messages = [warning.value for warning in at.warning]

    assert any("No known damaging moves are selected" in message for message in info_messages), {
        "info": info_messages,
        "warnings": warning_messages,
    }


def test_move_lookup_failure_preserves_selection(monkeypatch):
    at = run_app_with_team("garchomp")
    at.multiselect(key="moves_garchomp").set_value(["earthquake"]).run()

    def unavailable(name):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(move_ui, "cached_learnable_moves", unavailable)
    at.run()

    assert not at.exception
    assert at.multiselect(key="moves_garchomp").value == ["earthquake"]
    assert any("Existing selections are preserved" in warning.value for warning in at.warning)


def test_removed_member_moves_do_not_return_when_readded():
    at = run_app_with_team("garchomp,tyranitar")
    at.multiselect(key="moves_garchomp").set_value(["earthquake"]).run()

    at.multiselect(key="team").set_value(["tyranitar"]).run()
    assert not at.exception

    at.multiselect(key="team").set_value(["tyranitar", "garchomp"]).run()

    assert not at.exception
    assert at.multiselect(key="moves_garchomp").value == []


def test_swap_and_undo_preserve_supported_build_state():
    at = run_app_with_team("garchomp,tyranitar")

    at.multiselect(key="moves_garchomp").set_value(["earthquake"]).run()
    at.multiselect(key="moves_tyranitar").set_value(["ice-beam"]).run()
    at.multiselect(key="locked_members").set_value(["garchomp"]).run()

    at = apply_first_matchup_swap(at)
    assert not at.exception

    current_team = at.multiselect(key="team").value
    incoming = next(name for name in current_team if name not in {"garchomp", "tyranitar"})

    assert at.multiselect(key="moves_garchomp").value == ["earthquake"]
    assert at.multiselect(key=f"moves_{incoming}").value == []
    assert at.multiselect(key="locked_members").value == ["garchomp"]

    at.button(key="undo_swap").click().run()

    assert not at.exception
    assert at.multiselect(key="team").value == ["garchomp", "tyranitar"]
    assert at.multiselect(key="moves_garchomp").value == ["earthquake"]
    assert at.multiselect(key="moves_tyranitar").value == ["ice-beam"]
    assert at.multiselect(key="locked_members").value == ["garchomp"]
    assert at.multiselect(key="opponent_team").value == ["ferrothorn"]


def mock_team_upload(monkeypatch, contents: str | bytes):
    """Provide uploaded bytes while keeping the real load button and callback."""
    raw = contents.encode("utf-8") if isinstance(contents, str) else contents

    monkeypatch.setattr(
        st,
        "file_uploader",
        lambda *args, **kwargs: BytesIO(raw),
    )


def saved_build():
    return TeamState(
        members=(
            TeamMember(
                "garchomp",
                moves=("earthquake",),
                locked=True,
            ),
            TeamMember(
                "tyranitar",
                moves=("ice-beam",),
            ),
        )
    )


def test_json_load_restores_build_order_url_and_preserves_opponents(monkeypatch):
    mock_team_upload(monkeypatch, dump_team(saved_build()))
    at = run_app_with_team("dragonite")

    at.multiselect(key="moves_dragonite").set_value(["ice-beam"]).run()
    at.multiselect(key="opponent_team").set_value(["ferrothorn"]).run()

    at.button(key="load_team_json").click().run()

    assert not at.exception
    assert at.multiselect(key="team").value == ["garchomp", "tyranitar"]
    assert at.multiselect(key="moves_garchomp").value == ["earthquake"]
    assert at.multiselect(key="moves_tyranitar").value == ["ice-beam"]
    assert at.multiselect(key="locked_members").value == ["garchomp"]
    assert at.multiselect(key="opponent_team").value == ["ferrothorn"]

    url_team = at.query_params["team"]
    assert url_team in ("garchomp,tyranitar", ["garchomp,tyranitar"])

    at.multiselect(key="team").set_value(["garchomp", "tyranitar", "dragonite"]).run()

    assert not at.exception
    assert at.multiselect(key="moves_dragonite").value == []


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("{", "valid JSON"),
        ('{"schema_version": 2, "team": []}', "schema version"),
        (
            '{"schema_version": 1, "team": ['
            '{"species": "missingno", "moves": [], "locked": false}]}',
            "unrecognized species",
        ),
    ],
    ids=["invalid-json", "unsupported-version", "unknown-species"],
)
def test_failed_json_load_preserves_build_url_undo_and_preview(
    monkeypatch,
    contents,
    message,
):
    mock_team_upload(monkeypatch, contents)
    at = run_app_with_team("garchomp,tyranitar")
    at.multiselect(key="moves_garchomp").set_value(["earthquake"]).run()
    at.multiselect(key="locked_members").set_value(["garchomp"]).run()

    at = apply_first_matchup_swap(at)
    at.button(key="matchup_swap_0").click().run()
    assert not at.exception

    before_team = list(at.multiselect(key="team").value)
    before_url = at.query_params["team"]
    before_snapshot = at.session_state["team_state"]
    before_undo = at.session_state["team_before_swap"]
    before_last_swap = at.session_state["last_swap"]
    before_preview = at.session_state["pending_swap"]

    at.button(key="load_team_json").click().run()

    assert not at.exception
    assert at.multiselect(key="team").value == before_team
    assert at.multiselect(key="moves_garchomp").value == ["earthquake"]
    assert at.multiselect(key="locked_members").value == ["garchomp"]
    assert at.multiselect(key="opponent_team").value == ["ferrothorn"]
    assert at.query_params["team"] == before_url
    assert at.session_state["team_state"] == before_snapshot
    assert at.session_state["team_before_swap"] == before_undo
    assert at.session_state["last_swap"] == before_last_swap
    assert at.session_state["pending_swap"] == before_preview
    assert any(message in error.value for error in at.error)
    assert any(button.key == "undo_swap" for button in at.button)
    assert any(button.key == "confirm_swap_preview" for button in at.button)


def test_successful_json_load_clears_undo_and_preview(monkeypatch):
    mock_team_upload(monkeypatch, dump_team(saved_build()))
    at = run_app_with_team("garchomp,tyranitar")
    at = apply_first_matchup_swap(at)

    at.button(key="matchup_swap_0").click().run()
    assert not at.exception
    assert any(button.key == "undo_swap" for button in at.button)
    assert any(button.key == "confirm_swap_preview" for button in at.button)

    at.button(key="load_team_json").click().run()

    assert not at.exception
    assert at.multiselect(key="team").value == ["garchomp", "tyranitar"]
    assert at.multiselect(key="opponent_team").value == ["ferrothorn"]
    assert not any(button.key == "undo_swap" for button in at.button)
    assert not any(button.key == "confirm_swap_preview" for button in at.button)
    assert any(success.value == "Saved team loaded." for success in at.success)


def test_json_load_accepts_empty_team_and_removes_url(monkeypatch):
    mock_team_upload(monkeypatch, dump_team(TeamState()))
    at = run_app_with_team("garchomp")
    at.multiselect(key="moves_garchomp").set_value(["earthquake"]).run()
    at.multiselect(key="locked_members").set_value(["garchomp"]).run()

    at.button(key="load_team_json").click().run()

    assert not at.exception
    assert at.multiselect(key="team").value == []
    assert at.multiselect(key="locked_members").value == []
    assert "team" not in at.query_params
    assert any(info.value == "Pick at least one Pokémon to start." for info in at.info)

    at.multiselect(key="team").set_value(["garchomp"]).run()

    assert not at.exception
    assert at.multiselect(key="moves_garchomp").value == []


def test_json_load_button_disabled_without_file():
    at = run_app()

    assert not at.exception
    assert at.button(key="load_team_json").disabled


def test_json_download_contains_current_supported_build(monkeypatch):
    downloads = []
    original_download_button = st.download_button

    def capture_download(*args, **kwargs):
        if kwargs.get("key") == "download_team_json":
            downloads.append(kwargs["data"])
        return original_download_button(*args, **kwargs)

    monkeypatch.setattr(st, "download_button", capture_download)

    at = run_app_with_team("garchomp,tyranitar")
    at.multiselect(key="moves_garchomp").set_value(["earthquake"]).run()
    at.multiselect(key="moves_tyranitar").set_value(["ice-beam"]).run()
    at.multiselect(key="locked_members").set_value(["garchomp"]).run()

    assert not at.exception
    assert downloads
    assert load_team(downloads[-1]) == saved_build()


def select_available_pool(at, names):
    at.multiselect(key="available_pokemon").set_value(names).run()
    assert not at.exception

    at.radio(key="candidate_source").set_value("My available Pokémon").run()
    assert not at.exception

    return at


def test_available_pool_restricts_both_swap_engines():
    at = run_app_with_team("garchomp,tyranitar")
    at = select_available_pool(at, ["dragonite"])

    at.multiselect(key="opponent_team").set_value(["ferrothorn"]).run()
    at.checkbox(key="matchup_improvements_only").uncheck().run()

    assert not at.exception

    general = next(
        element.value
        for element in at.dataframe
        if {"candidate", "replaces", "improvement"}.issubset(element.value.columns)
    )
    targeted = next(
        element.value
        for element in at.dataframe
        if {"candidate", "replaces", "pressure_improvement"}.issubset(element.value.columns)
    )

    assert general["candidate"].tolist() == ["dragonite"]
    assert targeted["candidate"].tolist() == ["dragonite"]


@pytest.mark.parametrize(
    "pool",
    [[], ["garchomp", "tyranitar"]],
    ids=["empty-pool", "current-members-only"],
)
def test_pool_without_replacements_keeps_team_analysis_available(pool):
    at = run_app_with_team("garchomp,tyranitar")
    at = select_available_pool(at, pool)

    at.multiselect(key="opponent_team").set_value(["ferrothorn"]).run()

    assert not at.exception
    assert at.multiselect(key="team").value == ["garchomp", "tyranitar"]
    assert len(at.metric) >= 5
    assert "Team" in [header.value for header in at.subheader]
    assert not any(
        button.key and button.key.startswith(("swap_", "matchup_swap_")) for button in at.button
    )
    assert any(info.value == "No eligible single swaps are available." for info in at.info)


def test_available_pool_preserves_build_locks_and_opponents():
    at = run_app_with_team("garchomp,tyranitar")
    at.multiselect(key="moves_garchomp").set_value(["earthquake"]).run()
    at.multiselect(key="locked_members").set_value(["garchomp"]).run()
    at.multiselect(key="opponent_team").set_value(["ferrothorn"]).run()

    before_url = at.query_params["team"]
    at = select_available_pool(at, ["dragonite", "togekiss"])

    assert not at.exception
    assert at.multiselect(key="team").value == ["garchomp", "tyranitar"]
    assert at.multiselect(key="moves_garchomp").value == ["earthquake"]
    assert at.multiselect(key="locked_members").value == ["garchomp"]
    assert at.multiselect(key="opponent_team").value == ["ferrothorn"]
    assert at.query_params["team"] == before_url

    at.checkbox(key="matchup_improvements_only").uncheck().run()

    for element in at.dataframe:
        table = element.value
        if {"candidate", "replaces"}.issubset(table.columns):
            assert set(table["candidate"]) <= {"dragonite", "togekiss"}
            assert "garchomp" not in set(table["replaces"])


def test_pool_changes_clear_preview_and_preserve_undo():
    at = run_app_with_team("garchomp,tyranitar")
    at = apply_first_matchup_swap(at)
    before_team = list(at.multiselect(key="team").value)
    before_undo = at.session_state["team_before_swap"]

    at.button(key="matchup_swap_0").click().run()
    assert not at.exception
    assert any(button.key == "confirm_swap_preview" for button in at.button)

    at.multiselect(key="available_pokemon").set_value(["dragonite"]).run()

    assert not at.exception
    assert at.multiselect(key="team").value == before_team
    assert at.session_state["team_before_swap"] == before_undo
    assert any(button.key == "undo_swap" for button in at.button)
    assert not any(button.key == "confirm_swap_preview" for button in at.button)


def test_available_pool_selections_survive_mode_changes():
    at = run_app_with_team("garchomp,tyranitar")
    at = select_available_pool(at, ["dragonite", "togekiss"])

    at.radio(key="candidate_source").set_value("Current recommendation pool").run()
    assert not at.exception
    assert at.multiselect(key="available_pokemon").value == [
        "dragonite",
        "togekiss",
    ]

    at.radio(key="candidate_source").set_value("My available Pokémon").run()

    assert not at.exception
    assert at.multiselect(key="available_pokemon").value == [
        "dragonite",
        "togekiss",
    ]


def test_available_pool_accepts_below_threshold_candidate(monkeypatch):
    low_stats = {stat: 20 for stat in FAKE_STATS}

    monkeypatch.setattr(
        threat_ui,
        "cached_pokemon",
        lambda: {
            name: {
                "types": types,
                "stats": low_stats if name == "dragonite" else FAKE_STATS,
            }
            for name, types in FAKE_TYPES.items()
        },
    )

    at = run_app_with_team("garchomp,tyranitar")
    assert not at.exception

    default_swaps = next(
        element.value
        for element in at.dataframe
        if {"candidate", "replaces", "improvement"}.issubset(element.value.columns)
    )
    assert "dragonite" not in set(default_swaps["candidate"])

    at = select_available_pool(at, ["dragonite"])
    at.multiselect(key="opponent_team").set_value(["ferrothorn"]).run()
    at.checkbox(key="matchup_improvements_only").uncheck().run()

    assert not at.exception

    swap_tables = [
        element.value
        for element in at.dataframe
        if {"candidate", "replaces"}.issubset(element.value.columns)
    ]
    assert len(swap_tables) == 2

    for table in swap_tables:
        assert table["candidate"].tolist() == ["dragonite"]


@pytest.mark.parametrize(
    "lookup_fails",
    [False, True],
    ids=["lookup-success", "lookup-failure"],
)
def test_available_pool_handles_uncached_candidate(monkeypatch, lookup_fails):
    monkeypatch.setattr(
        threat_ui,
        "cached_pokemon",
        lambda: {
            name: {
                "types": types,
                "stats": FAKE_STATS,
            }
            for name, types in FAKE_TYPES.items()
            if name != "dragonite"
        },
    )

    lookups = []

    def lookup_types(name):
        lookups.append(name)
        if name == "dragonite" and lookup_fails:
            raise requests.ConnectionError("offline")
        return FAKE_TYPES[name]

    monkeypatch.setattr(fetch, "get_types", lookup_types)

    at = run_app_with_team("garchomp,tyranitar")
    at = select_available_pool(at, ["dragonite", "togekiss"])

    at.multiselect(key="opponent_team").set_value(["ferrothorn"]).run()
    at.checkbox(key="matchup_improvements_only").uncheck().run()

    assert not at.exception
    assert "dragonite" in lookups
    assert at.multiselect(key="team").value == ["garchomp", "tyranitar"]

    expected = {"togekiss"} if lookup_fails else {"dragonite", "togekiss"}
    swap_tables = [
        element.value
        for element in at.dataframe
        if {"candidate", "replaces"}.issubset(element.value.columns)
    ]
    assert len(swap_tables) == 2

    for table in swap_tables:
        assert set(table["candidate"]) == expected

    if lookup_fails:
        assert any(
            "Dragonite" in warning.value and "available replacement pool" in warning.value
            for warning in at.warning
        )


def test_candidate_mode_change_clears_preview_and_preserves_undo():
    at = run_app_with_team("garchomp,tyranitar")
    at = apply_first_matchup_swap(at)

    before_team = list(at.multiselect(key="team").value)
    before_url = at.query_params["team"]
    before_undo = at.session_state["team_before_swap"]

    at.button(key="matchup_swap_0").click().run()
    assert not at.exception
    assert any(button.key == "confirm_swap_preview" for button in at.button)

    at.radio(key="candidate_source").set_value("My available Pokémon").run()

    assert not at.exception
    assert at.multiselect(key="team").value == before_team
    assert at.query_params["team"] == before_url
    assert at.session_state["team_before_swap"] == before_undo
    assert at.multiselect(key="opponent_team").value == ["ferrothorn"]
    assert any(button.key == "undo_swap" for button in at.button)
    assert not any(button.key == "confirm_swap_preview" for button in at.button)


def test_meta_threats_with_empty_usage_keeps_app_running(monkeypatch):
    usage = threat_ui.cached_usage()
    monkeypatch.setattr(
        threat_ui,
        "cached_usage",
        lambda: {**usage, "top": []},
    )

    at = run_app_with_team("garchomp,tyranitar")

    assert not at.exception
    assert any(info.value == "No Pokémon are listed in the saved usage data." for info in at.info)
    assert len(at.metric) >= 5


def test_meta_threats_without_cache_matches_keeps_app_running(monkeypatch):
    usage = threat_ui.cached_usage()
    template = usage["top"][0]
    missing = {
        **template,
        "name": "not-in-cache",
        "smogon_name": "Not In Cache",
    }

    monkeypatch.setattr(
        threat_ui,
        "cached_usage",
        lambda: {**usage, "top": [missing]},
    )

    at = run_app_with_team("garchomp,tyranitar")

    assert not at.exception
    assert any(
        "No usage-list Pokémon match the local Pokémon cache." in info.value for info in at.info
    )
    assert len(at.metric) >= 5
    assert not any(
        {"threat", "usage %"}.issubset(element.value.columns) for element in at.dataframe
    )


def test_meta_threats_reports_partial_cache_matches(monkeypatch):
    usage = threat_ui.cached_usage()
    template = usage["top"][0]

    available = {
        **template,
        "name": "garchomp",
        "smogon_name": "Garchomp",
    }
    missing = {
        **template,
        "name": "not-in-cache",
        "smogon_name": "Not In Cache",
    }

    monkeypatch.setattr(
        threat_ui,
        "cached_usage",
        lambda: {**usage, "top": [available, missing]},
    )

    at = run_app_with_team("garchomp,tyranitar")

    assert not at.exception
    assert any("Analyzing 1 of 2 usage entries." in warning.value for warning in at.warning)

    table = next(
        element.value
        for element in at.dataframe
        if {"threat", "usage %"}.issubset(element.value.columns)
    )
    assert table["threat"].tolist() == ["Garchomp"]
    assert not any("every top-30" in success.value for success in at.success)


def test_bulk_pool_preview_does_not_change_pool_team_or_preview():
    at = run_app_with_team("garchomp,tyranitar")
    at = select_available_pool(at, ["dragonite", "togekiss"])

    at.multiselect(key="opponent_team").set_value(["ferrothorn"]).run()
    at.checkbox(key="matchup_improvements_only").uncheck().run()
    at.button(key="matchup_swap_0").click().run()
    assert not at.exception

    before_preview = at.session_state["pending_swap"]
    before_url = at.query_params["team"]

    at.text_area(key="pool_paste").input("Dragonite, dragonite, Missingno").run()

    assert not at.exception
    assert at.multiselect(key="available_pokemon").value == [
        "dragonite",
        "togekiss",
    ]
    assert at.multiselect(key="team").value == ["garchomp", "tyranitar"]
    assert at.query_params["team"] == before_url
    assert at.session_state["pending_swap"] == before_preview
    assert any(
        "1 recognized species" in caption.value
        and "1 repeated species" in caption.value
        and "1 unrecognized entries" in caption.value
        for caption in at.caption
    )
    assert any("Missingno" in warning.value for warning in at.warning)


def test_bulk_pool_add_preserves_order_and_activates_custom_pool():
    at = run_app_with_team("garchomp,tyranitar")
    at.multiselect(key="available_pokemon").set_value(["togekiss", "dragonite"]).run()

    at.text_area(key="pool_paste").input("Dragonite, Ferrothorn, Gyarados, Ferrothorn").run()
    at.button(key="pool_add").click().run()

    assert not at.exception
    assert at.multiselect(key="available_pokemon").value == [
        "togekiss",
        "dragonite",
        "ferrothorn",
        "gyarados",
    ]
    assert at.radio(key="candidate_source").value == "My available Pokémon"
    assert at.multiselect(key="team").value == ["garchomp", "tyranitar"]
    assert any("Added 2 new Pokémon." in success.value for success in at.success)


def test_bulk_pool_replace_accepts_showdown_roster():
    at = run_app_with_team("garchomp,tyranitar")
    at = select_available_pool(at, ["dragonite", "togekiss"])

    at.radio(key="pool_input_format").set_value("Showdown roster").run()
    at.text_area(key="pool_paste").input(
        "Chompy (Garchomp) @ Choice Scarf\n- Earthquake\n\nFerrothorn @ Leftovers\n- Protect"
    ).run()
    at.button(key="pool_replace").click().run()

    assert not at.exception
    assert at.multiselect(key="available_pokemon").value == [
        "garchomp",
        "ferrothorn",
    ]
    assert at.multiselect(key="team").value == ["garchomp", "tyranitar"]
    assert at.multiselect(key="moves_garchomp").value == []


@pytest.mark.parametrize(
    "contents",
    ["", "Missingno, Not A Pokemon"],
    ids=["empty-input", "unknown-only"],
)
def test_invalid_bulk_input_disables_actions_and_preserves_state(contents):
    at = run_app_with_team("garchomp,tyranitar")
    at = select_available_pool(at, ["dragonite", "togekiss"])
    at = apply_first_matchup_swap(at)

    at.button(key="matchup_swap_0").click().run()
    assert not at.exception

    before_team = list(at.multiselect(key="team").value)
    before_undo = at.session_state["team_before_swap"]
    before_preview = at.session_state["pending_swap"]

    at.text_area(key="pool_paste").input(contents).run()

    assert not at.exception
    assert at.button(key="pool_add").disabled
    assert at.button(key="pool_replace").disabled
    assert at.multiselect(key="available_pokemon").value == [
        "dragonite",
        "togekiss",
    ]
    assert at.multiselect(key="team").value == before_team
    assert at.session_state["team_before_swap"] == before_undo
    assert at.session_state["pending_swap"] == before_preview


@pytest.mark.parametrize("button_key", ["pool_add", "pool_replace"])
def test_bulk_pool_apply_preserves_build_and_undo_but_clears_preview(button_key):
    at = run_app_with_team("garchomp,tyranitar")
    at.multiselect(key="moves_garchomp").set_value(["earthquake"]).run()
    at.multiselect(key="locked_members").set_value(["garchomp"]).run()
    at = apply_first_matchup_swap(at)

    at.button(key="matchup_swap_0").click().run()
    assert not at.exception

    before_team = list(at.multiselect(key="team").value)
    before_url = at.query_params["team"]
    before_undo = at.session_state["team_before_swap"]

    at.text_area(key="pool_paste").input("Dragonite, Togekiss").run()
    at.button(key=button_key).click().run()

    assert not at.exception
    assert at.multiselect(key="team").value == before_team
    assert at.multiselect(key="moves_garchomp").value == ["earthquake"]
    assert at.multiselect(key="locked_members").value == ["garchomp"]
    assert at.multiselect(key="opponent_team").value == ["ferrothorn"]
    assert at.query_params["team"] == before_url
    assert at.session_state["team_before_swap"] == before_undo
    assert any(button.key == "undo_swap" for button in at.button)
    assert not any(button.key == "confirm_swap_preview" for button in at.button)


def saved_analysis_workspace():
    return WorkspaceState(
        team=saved_build(),
        available_pokemon=("togekiss", "dragonite"),
        candidate_source="custom",
        opponent_team=("ferrothorn", "gyarados"),
        matchup_improvements_only=False,
    )


def test_workspace_load_restores_all_settings_and_clears_history(monkeypatch):
    mock_team_upload(
        monkeypatch,
        dump_workspace(saved_analysis_workspace()),
    )

    at = run_app_with_team("garchomp,tyranitar")
    at = apply_first_matchup_swap(at)
    at.button(key="matchup_swap_0").click().run()
    assert not at.exception

    at.text_area(key="showdown_paste").input("Old team paste").run()
    at.text_area(key="pool_paste").input("Dragonite").run()

    at.button(key="load_workspace_json").click().run()

    assert not at.exception
    assert at.multiselect(key="team").value == ["garchomp", "tyranitar"]
    assert at.multiselect(key="moves_garchomp").value == ["earthquake"]
    assert at.multiselect(key="moves_tyranitar").value == ["ice-beam"]
    assert at.multiselect(key="locked_members").value == ["garchomp"]
    assert at.multiselect(key="available_pokemon").value == [
        "togekiss",
        "dragonite",
    ]
    assert at.radio(key="candidate_source").value == "My available Pokémon"
    assert at.multiselect(key="opponent_team").value == [
        "ferrothorn",
        "gyarados",
    ]
    assert at.checkbox(key="matchup_improvements_only").value is False
    assert at.text_area(key="showdown_paste").value == ""
    assert at.text_area(key="pool_paste").value == ""
    assert not any(button.key == "undo_swap" for button in at.button)
    assert not any(button.key == "confirm_swap_preview" for button in at.button)

    url_team = at.query_params["team"]
    assert url_team in ("garchomp,tyranitar", ["garchomp,tyranitar"])
    assert any(success.value == "Workspace loaded." for success in at.success)


@pytest.mark.parametrize(
    "problem",
    ["invalid-json", "team-only", "unknown-pool-species"],
)
def test_failed_workspace_load_preserves_existing_state(monkeypatch, problem):
    if problem == "invalid-json":
        contents = "{"
    elif problem == "team-only":
        contents = dump_team(saved_build())
    else:
        contents = dump_workspace(
            WorkspaceState(
                available_pokemon=("missingno",),
                candidate_source="custom",
            )
        )

    mock_team_upload(monkeypatch, contents)

    at = run_app_with_team("garchomp,tyranitar")
    at.multiselect(key="moves_garchomp").set_value(["earthquake"]).run()
    at.multiselect(key="locked_members").set_value(["garchomp"]).run()
    at = select_available_pool(at, ["dragonite", "togekiss"])
    at = apply_first_matchup_swap(at)
    at.button(key="matchup_swap_0").click().run()
    assert not at.exception

    before_team = list(at.multiselect(key="team").value)
    before_url = at.query_params["team"]
    before_undo = at.session_state["team_before_swap"]
    before_preview = at.session_state["pending_swap"]

    at.button(key="load_workspace_json").click().run()

    assert not at.exception
    assert at.multiselect(key="team").value == before_team
    assert at.multiselect(key="moves_garchomp").value == ["earthquake"]
    assert at.multiselect(key="locked_members").value == ["garchomp"]
    assert at.multiselect(key="available_pokemon").value == [
        "dragonite",
        "togekiss",
    ]
    assert at.radio(key="candidate_source").value == "My available Pokémon"
    assert at.multiselect(key="opponent_team").value == ["ferrothorn"]
    assert at.checkbox(key="matchup_improvements_only").value is False
    assert at.query_params["team"] == before_url
    assert at.session_state["team_before_swap"] == before_undo
    assert at.session_state["pending_swap"] == before_preview
    assert at.error


def test_empty_team_workspace_preserves_hidden_opponents_and_filter(monkeypatch):
    workspace = WorkspaceState(
        available_pokemon=("dragonite",),
        candidate_source="custom",
        opponent_team=("ferrothorn",),
        matchup_improvements_only=False,
    )
    mock_team_upload(monkeypatch, dump_workspace(workspace))

    at = run_app_with_team("garchomp")
    at.button(key="load_workspace_json").click().run()
    at.run()

    assert not at.exception
    assert at.multiselect(key="team").value == []
    assert "team" not in at.query_params
    assert at.session_state["opponent_team"] == ["ferrothorn"]
    assert at.session_state["matchup_improvements_only"] is False
    assert at.multiselect(key="available_pokemon").value == ["dragonite"]

    at.multiselect(key="team").set_value(["garchomp"]).run()

    assert not at.exception
    assert at.multiselect(key="opponent_team").value == ["ferrothorn"]
    assert at.checkbox(key="matchup_improvements_only").value is False


def test_matchup_filter_survives_hidden_widget():
    at = run_app_with_team("garchomp,tyranitar")
    at.multiselect(key="opponent_team").set_value(["ferrothorn"]).run()
    at.checkbox(key="matchup_improvements_only").uncheck().run()

    at.multiselect(key="opponent_team").set_value([]).run()
    at.run()

    assert not at.exception
    assert at.session_state["matchup_improvements_only"] is False

    at.multiselect(key="opponent_team").set_value(["ferrothorn"]).run()

    assert not at.exception
    assert at.checkbox(key="matchup_improvements_only").value is False


def test_workspace_load_button_disabled_without_file():
    at = run_app()

    assert not at.exception
    assert at.button(key="load_workspace_json").disabled


def test_workspace_download_contains_current_build_and_preferences(monkeypatch):
    downloads = []
    original_download_button = st.download_button

    def capture_download(*args, **kwargs):
        if kwargs.get("key") == "download_workspace_json":
            downloads.append(kwargs["data"])
        return original_download_button(*args, **kwargs)

    monkeypatch.setattr(st, "download_button", capture_download)

    at = run_app_with_team("garchomp,tyranitar")
    at.multiselect(key="moves_garchomp").set_value(["earthquake"]).run()
    at.multiselect(key="moves_tyranitar").set_value(["ice-beam"]).run()
    at.multiselect(key="locked_members").set_value(["garchomp"]).run()
    at = select_available_pool(at, ["togekiss", "dragonite"])
    at.multiselect(key="opponent_team").set_value(["ferrothorn", "gyarados"]).run()
    at.checkbox(key="matchup_improvements_only").uncheck().run()

    assert not at.exception
    assert downloads
    assert load_workspace(downloads[-1]) == saved_analysis_workspace()


def selected_move_tables(at):
    columns = {"Move", "Type", "Category", "Power", "Coverage"}

    return [element.value for element in at.dataframe if columns.issubset(element.value.columns)]


@pytest.mark.parametrize(
    ("move", "metadata", "category", "coverage", "power"),
    [
        (
            "earthquake",
            {
                "type": "ground",
                "damage_class": "physical",
                "power": 100,
            },
            "Physical",
            "Counted — damaging move type",
            100,
        ),
        (
            "swords-dance",
            {
                "type": "normal",
                "damage_class": "status",
                "power": None,
            },
            "Status",
            "Not counted — status move",
            None,
        ),
        (
            "unverified-move",
            None,
            "Unknown",
            "Unavailable — selection preserved",
            None,
        ),
        (
            "seismic-toss",
            {
                "type": "fighting",
                "damage_class": "physical",
                "power": None,
            },
            "Physical",
            "Counted — damaging move type",
            None,
        ),
    ],
    ids=["damaging", "status", "unknown", "missing-power"],
)
def test_selected_move_details_render(
    monkeypatch,
    move,
    metadata,
    category,
    coverage,
    power,
):
    monkeypatch.setattr(
        move_ui,
        "cached_learnable_moves",
        lambda name: [move],
    )
    monkeypatch.setattr(
        move_ui,
        "cached_move_cache",
        lambda: {} if metadata is None else {move: metadata},
    )

    at = run_app_with_team("garchomp")
    at.multiselect(key="moves_garchomp").set_value([move]).run()

    assert not at.exception
    assert at.multiselect(key="moves_garchomp").value == [move]

    tables = selected_move_tables(at)
    assert len(tables) == 1

    row = tables[0].iloc[0]
    assert row["Move"] == move.replace("-", " ").title()
    assert row["Category"] == category
    assert row["Coverage"] == coverage

    if metadata is None:
        assert row["Type"] == "Unknown"
    else:
        assert row["Type"] == metadata["type"].title()

    if power is None:
        assert pd.isna(row["Power"])
    else:
        assert row["Power"] == power


def test_empty_move_selection_does_not_render_details():
    at = run_app_with_team("garchomp")

    assert not at.exception
    assert selected_move_tables(at) == []
    assert any(info.value == "Pick some moves to see move-based coverage gaps." for info in at.info)


def test_selected_move_details_remain_after_learnset_failure(monkeypatch):
    monkeypatch.setattr(
        move_ui,
        "cached_move_cache",
        lambda: {
            "earthquake": {
                "type": "ground",
                "damage_class": "physical",
                "power": 100,
            }
        },
    )

    at = run_app_with_team("garchomp")
    at.multiselect(key="moves_garchomp").set_value(["earthquake"]).run()

    def unavailable(name):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(move_ui, "cached_learnable_moves", unavailable)
    at.run()

    assert not at.exception
    assert at.multiselect(key="moves_garchomp").value == ["earthquake"]

    tables = selected_move_tables(at)
    assert len(tables) == 1
    assert tables[0]["Move"].tolist() == ["Earthquake"]
    assert any("Existing selections are preserved" in warning.value for warning in at.warning)


@pytest.fixture
def fixed_loadouts(monkeypatch):
    monkeypatch.setattr(
        loadout_ui,
        "suggest_loadouts",
        lambda team, learnsets, stats, cache, chart: {
            name: ["earthquake", "ice-beam"] for name in team
        },
    )


def test_loadout_preview_and_cancel_do_not_change_build(fixed_loadouts):
    at = run_app_with_team("garchomp,tyranitar")
    at.multiselect(key="moves_garchomp").set_value(["earthquake"]).run()
    before_url = at.query_params["team"]

    at.button(key="preview_loadout_garchomp").click().run()

    assert not at.exception
    assert at.multiselect(key="moves_garchomp").value == ["earthquake"]
    assert at.multiselect(key="moves_tyranitar").value == []
    assert at.query_params["team"] == before_url
    assert any(button.key == "confirm_loadout" for button in at.button)

    at.button(key="cancel_loadout").click().run()

    assert not at.exception
    assert at.multiselect(key="moves_garchomp").value == ["earthquake"]
    assert not any(button.key == "confirm_loadout" for button in at.button)


def test_apply_loadout_changes_only_target_and_preserves_preferences(fixed_loadouts):
    at = run_app_with_team("garchomp,tyranitar")
    at.multiselect(key="moves_tyranitar").set_value(["ice-beam"]).run()
    at.multiselect(key="locked_members").set_value(["garchomp"]).run()
    at = select_available_pool(at, ["dragonite", "togekiss"])
    at.multiselect(key="opponent_team").set_value(["ferrothorn"]).run()
    before_url = at.query_params["team"]

    at.button(key="preview_loadout_garchomp").click().run()
    at.button(key="confirm_loadout").click().run()

    assert not at.exception
    assert at.multiselect(key="moves_garchomp").value == [
        "earthquake",
        "ice-beam",
    ]
    assert at.multiselect(key="moves_tyranitar").value == ["ice-beam"]
    assert at.multiselect(key="team").value == ["garchomp", "tyranitar"]
    assert at.multiselect(key="locked_members").value == ["garchomp"]
    assert at.multiselect(key="available_pokemon").value == [
        "dragonite",
        "togekiss",
    ]
    assert at.multiselect(key="opponent_team").value == ["ferrothorn"]
    assert at.query_params["team"] == before_url
    assert at.session_state["team_state"].members[0].moves == (
        "earthquake",
        "ice-beam",
    )


def test_manual_move_edit_dismisses_loadout_preview(fixed_loadouts):
    at = run_app_with_team("garchomp")
    at.button(key="preview_loadout_garchomp").click().run()
    assert not at.exception

    at.multiselect(key="moves_garchomp").set_value(["ice-beam"]).run()

    assert not at.exception
    assert at.multiselect(key="moves_garchomp").value == ["ice-beam"]
    assert not any(button.key == "confirm_loadout" for button in at.button)


def test_remove_and_readd_member_does_not_restore_loadout_preview(fixed_loadouts):
    at = run_app_with_team("garchomp,tyranitar")
    at.button(key="preview_loadout_garchomp").click().run()

    at.multiselect(key="team").set_value(["tyranitar"]).run()
    at.multiselect(key="team").set_value(["tyranitar", "garchomp"]).run()

    assert not at.exception
    assert at.multiselect(key="moves_garchomp").value == []
    assert not any(button.key == "confirm_loadout" for button in at.button)


def test_apply_loadout_clears_swap_preview_and_preserves_undo(fixed_loadouts):
    at = run_app_with_team("garchomp,tyranitar")
    at.multiselect(key="locked_members").set_value(["garchomp"]).run()
    at = apply_first_matchup_swap(at)
    before_undo = at.session_state["team_before_swap"]

    at.button(key="matchup_swap_0").click().run()
    at.button(key="preview_loadout_garchomp").click().run()
    assert not at.exception
    assert any(button.key == "confirm_swap_preview" for button in at.button)

    at.button(key="confirm_loadout").click().run()

    assert not at.exception
    assert at.multiselect(key="moves_garchomp").value == [
        "earthquake",
        "ice-beam",
    ]
    assert at.session_state["team_before_swap"] == before_undo
    assert any(button.key == "undo_swap" for button in at.button)
    assert not any(button.key == "confirm_swap_preview" for button in at.button)


def test_empty_loadout_has_disabled_preview(monkeypatch):
    monkeypatch.setattr(
        loadout_ui,
        "suggest_loadouts",
        lambda team, learnsets, stats, cache, chart: {name: [] for name in team},
    )

    at = run_app_with_team("garchomp")

    assert not at.exception
    assert at.button(key="preview_loadout_garchomp").disabled


def test_matching_loadout_has_disabled_preview(fixed_loadouts):
    at = run_app_with_team("garchomp")
    at.multiselect(key="moves_garchomp").set_value(["earthquake", "ice-beam"]).run()

    assert not at.exception
    assert at.button(key="preview_loadout_garchomp").disabled


def test_successful_team_import_dismisses_loadout_preview(fixed_loadouts):
    at = run_app_with_team("garchomp,tyranitar")
    at.button(key="preview_loadout_garchomp").click().run()

    at.text_area(key="showdown_paste").input(PASTE)
    at.button(key="import_btn").click().run()

    assert not at.exception
    assert not any(button.key == "confirm_loadout" for button in at.button)


def test_failed_team_import_preserves_loadout_preview(fixed_loadouts):
    at = run_app_with_team("garchomp,tyranitar")
    at.button(key="preview_loadout_garchomp").click().run()
    before = at.session_state["pending_loadout"]

    at.text_area(key="showdown_paste").input("Missingno @ Nothing")
    at.button(key="import_btn").click().run()

    assert not at.exception
    assert at.session_state["pending_loadout"] == before
    assert any(button.key == "confirm_loadout" for button in at.button)


@pytest.mark.parametrize("file_kind", ["team", "workspace"])
@pytest.mark.parametrize("valid_file", [True, False], ids=["valid", "rejected"])
def test_json_restore_handles_pending_loadout(
    monkeypatch,
    fixed_loadouts,
    file_kind,
    valid_file,
):
    if not valid_file:
        contents = "{"
    elif file_kind == "team":
        contents = dump_team(saved_build())
    else:
        contents = dump_workspace(saved_analysis_workspace())

    mock_team_upload(monkeypatch, contents)

    at = run_app_with_team("garchomp,tyranitar")
    at.multiselect(key="moves_garchomp").set_value(["earthquake"]).run()
    at.button(key="preview_loadout_garchomp").click().run()
    assert not at.exception

    before_proposal = at.session_state["pending_loadout"]
    button_key = "load_team_json" if file_kind == "team" else "load_workspace_json"

    at.button(key=button_key).click().run()

    assert not at.exception

    if valid_file:
        assert not any(button.key == "confirm_loadout" for button in at.button)
        assert at.multiselect(key="moves_garchomp").value == ["earthquake"]
        assert at.multiselect(key="moves_tyranitar").value == ["ice-beam"]
    else:
        assert at.session_state["pending_loadout"] == before_proposal
        assert any(button.key == "confirm_loadout" for button in at.button)
        assert at.multiselect(key="moves_garchomp").value == ["earthquake"]
        assert at.multiselect(key="moves_tyranitar").value == []


def test_undo_after_loadout_apply_restores_complete_pre_swap_build(fixed_loadouts):
    at = run_app_with_team("garchomp,tyranitar")
    at.multiselect(key="moves_garchomp").set_value(["earthquake"]).run()
    at.multiselect(key="moves_tyranitar").set_value(["ice-beam"]).run()
    at.multiselect(key="locked_members").set_value(["garchomp"]).run()

    at = apply_first_matchup_swap(at)
    at.button(key="preview_loadout_garchomp").click().run()
    at.button(key="confirm_loadout").click().run()

    assert not at.exception
    assert at.multiselect(key="moves_garchomp").value == [
        "earthquake",
        "ice-beam",
    ]

    at.button(key="undo_swap").click().run()

    assert not at.exception
    assert at.multiselect(key="team").value == ["garchomp", "tyranitar"]
    assert at.multiselect(key="moves_garchomp").value == ["earthquake"]
    assert at.multiselect(key="moves_tyranitar").value == ["ice-beam"]
    assert at.multiselect(key="locked_members").value == ["garchomp"]
    assert not any(button.key == "confirm_loadout" for button in at.button)


def test_applied_loadout_is_in_team_and_workspace_downloads(
    monkeypatch,
    fixed_loadouts,
):
    downloads = {}
    original_download_button = st.download_button

    def capture_download(*args, **kwargs):
        key = kwargs.get("key")
        if key in {"download_team_json", "download_workspace_json"}:
            downloads[key] = kwargs["data"]
        return original_download_button(*args, **kwargs)

    monkeypatch.setattr(st, "download_button", capture_download)

    at = run_app_with_team("garchomp,tyranitar")
    at.multiselect(key="moves_tyranitar").set_value(["ice-beam"]).run()

    at.button(key="preview_loadout_garchomp").click().run()
    at.button(key="confirm_loadout").click().run()

    assert not at.exception

    team = load_team(downloads["download_team_json"])
    workspace = load_workspace(downloads["download_workspace_json"])

    assert team.members[0].moves == ("earthquake", "ice-beam")
    assert team.members[1].moves == ("ice-beam",)
    assert workspace.team == team


@pytest.fixture
def captured_showdown_download(monkeypatch):
    downloads = []
    original_download_button = st.download_button

    def capture_download(*args, **kwargs):
        if kwargs.get("key") == "download_showdown":
            downloads.append(kwargs["data"])
        return original_download_button(*args, **kwargs)

    monkeypatch.setattr(st, "download_button", capture_download)
    return downloads


def test_showdown_download_includes_manual_selected_moves(
    monkeypatch,
    captured_showdown_download,
):
    monkeypatch.setattr(
        move_ui,
        "cached_learnable_moves",
        lambda name: ["earthquake", "swords-dance", "ice-beam"],
    )
    monkeypatch.setattr(
        move_ui,
        "cached_move_cache",
        lambda: {
            "earthquake": {
                "type": "ground",
                "damage_class": "physical",
                "power": 100,
            },
            "swords-dance": {
                "type": "normal",
                "damage_class": "status",
                "power": None,
            },
            "ice-beam": {
                "type": "ice",
                "damage_class": "special",
                "power": 90,
            },
        },
    )

    at = run_app_with_team("garchomp,tyranitar")
    at.multiselect(key="moves_garchomp").set_value(["swords-dance", "earthquake"]).run()
    at.multiselect(key="moves_tyranitar").set_value(["ice-beam"]).run()

    assert not at.exception

    parsed = parse_showdown(captured_showdown_download[-1])

    assert [mon.species for mon in parsed] == ["garchomp", "tyranitar"]
    assert parsed[0].moves == ["swords-dance", "earthquake"]
    assert parsed[1].moves == ["ice-beam"]


def test_showdown_download_includes_imported_moves(
    captured_showdown_download,
):
    at = run_app()
    at.text_area(key="showdown_paste").input(PASTE)
    at.button(key="import_btn").click().run()

    assert not at.exception

    parsed = parse_showdown(captured_showdown_download[-1])

    assert [mon.species for mon in parsed] == ["garchomp", "tyranitar"]
    assert parsed[0].moves == ["earthquake"]
    assert parsed[1].moves == ["crunch"]


def test_showdown_download_includes_applied_loadout(
    fixed_loadouts,
    captured_showdown_download,
):
    at = run_app_with_team("garchomp,tyranitar")
    at.multiselect(key="moves_tyranitar").set_value(["ice-beam"]).run()

    at.button(key="preview_loadout_garchomp").click().run()
    at.button(key="confirm_loadout").click().run()

    assert not at.exception

    parsed = parse_showdown(captured_showdown_download[-1])

    assert parsed[0].species == "garchomp"
    assert parsed[0].moves == ["earthquake", "ice-beam"]
    assert parsed[1].species == "tyranitar"
    assert parsed[1].moves == ["ice-beam"]


@pytest.mark.parametrize(
    "failed_names",
    [
        pytest.param({"tyranitar"}, id="partial-type-failure"),
        pytest.param(
            {"garchomp", "tyranitar"},
            id="all-type-lookups-fail",
        ),
    ],
)
def test_showdown_download_preserves_team_when_types_fail(
    monkeypatch,
    captured_showdown_download,
    failed_names,
):
    at = run_app_with_team("garchomp,tyranitar")
    at.multiselect(key="moves_garchomp").set_value(["earthquake"]).run()
    at.multiselect(key="moves_tyranitar").set_value(["ice-beam"]).run()

    def lookup_types(name, cache):
        if name in failed_names:
            raise requests.ConnectionError("offline")
        return FAKE_TYPES[name]

    monkeypatch.setattr(fetch, "types_cache_first", lookup_types)
    st.cache_data.clear()
    at.run()

    assert not at.exception

    parsed = parse_showdown(captured_showdown_download[-1])

    assert [mon.species for mon in parsed] == ["garchomp", "tyranitar"]
    assert parsed[0].moves == ["earthquake"]
    assert parsed[1].moves == ["ice-beam"]
    assert any("Couldn't load" in warning.value for warning in at.warning)


def test_showdown_download_disabled_for_empty_team(
    captured_showdown_download,
):
    at = run_app_with_team("garchomp")
    at.multiselect(key="team").set_value([]).run()

    assert not at.exception
    assert captured_showdown_download[-1] == ""


@pytest.fixture
def naming_species(monkeypatch):
    additions = {
        "mr-mime": ["psychic", "fairy"],
        "nidoran-f": ["poison"],
        "nidoran-m": ["poison"],
        "rotom-wash": ["electric", "water"],
        "farfetchd": ["normal", "flying"],
        "type-null": ["normal"],
    }

    for name, types in additions.items():
        monkeypatch.setitem(FAKE_TYPES, name, types)


@pytest.mark.parametrize(
    ("paste", "expected"),
    [
        (
            "Nidoran♀\n- Earthquake\n\nNidoran♂\n- Ice Beam",
            ["nidoran-f", "nidoran-m"],
        ),
        (
            "Mimey (MrMime) (M) @ Leftovers\n- Earthquake\n\nRotomWash @ Leftovers\n- Ice Beam",
            ["mr-mime", "rotom-wash"],
        ),
    ],
    ids=["gender-symbols", "compact-aliases"],
)
def test_naming_showdown_import_resolves_species(
    naming_species,
    paste,
    expected,
):
    at = run_app_with_team("garchomp,tyranitar")

    at.text_area(key="showdown_paste").input(paste)
    at.button(key="import_btn").click().run()

    assert not at.exception
    assert at.multiselect(key="team").value == expected
    assert at.multiselect(key=f"moves_{expected[0]}").value == ["earthquake"]
    assert at.multiselect(key=f"moves_{expected[1]}").value == ["ice-beam"]

    url_team = at.query_params["team"]
    assert url_team in (",".join(expected), [",".join(expected)])


@pytest.mark.parametrize(
    "input_format",
    ["Pokémon names", "Showdown roster"],
)
def test_naming_bulk_pool_resolves_and_deduplicates_aliases(
    naming_species,
    input_format,
):
    at = run_app_with_team("garchomp,tyranitar")
    at.radio(key="pool_input_format").set_value(input_format).run()

    entries = ["MrMime", "Mr. Mime", "Nidoran♀", "Nidoran♂", "RotomWash"]
    separator = ", " if input_format == "Pokémon names" else "\n\n"

    at.text_area(key="pool_paste").input(separator.join(entries)).run()

    assert not at.exception
    assert any(
        "4 recognized species" in caption.value and "1 repeated species" in caption.value
        for caption in at.caption
    )

    at.button(key="pool_replace").click().run()

    assert not at.exception
    assert at.multiselect(key="available_pokemon").value == [
        "mr-mime",
        "nidoran-f",
        "nidoran-m",
        "rotom-wash",
    ]
    assert at.multiselect(key="team").value == ["garchomp", "tyranitar"]


def test_naming_showdown_download_uses_mapped_species_names(
    naming_species,
    captured_showdown_download,
):
    species = [
        "mr-mime",
        "nidoran-f",
        "nidoran-m",
        "rotom-wash",
        "farfetchd",
        "type-null",
    ]
    at = run_app_with_team(",".join(species))

    assert not at.exception

    contents = captured_showdown_download[-1]
    headers = [block.splitlines()[0] for block in contents.strip().split("\n\n")]

    assert headers == [
        "Mr. Mime",
        "Nidoran-F",
        "Nidoran-M",
        "Rotom-Wash",
        "Farfetch’d",
        "Type: Null",
    ]
    assert [mon.species for mon in parse_showdown(contents)] == species


def test_team_controls_show_heading_and_selected_counts():
    at = run_app_with_team("garchomp,tyranitar")
    at.multiselect(key="locked_members").set_value(["garchomp"]).run()

    assert not at.exception
    assert at.subheader[0].value == "Build your team"
    assert any(
        caption.value == "Team: 2/6 Pokémon selected · 1 locked against replacement"
        for caption in at.caption
    )
    assert any(
        "Workspace JSON: team, replacement pool, opponents, and settings" in caption.value
        for caption in at.caption
    )


def test_empty_team_keeps_setup_and_file_controls_available():
    at = run_app_with_team("garchomp")
    at.multiselect(key="team").set_value([]).run()

    assert not at.exception
    assert any(
        caption.value == "Team: 0/6 Pokémon selected · 0 locked against replacement"
        for caption in at.caption
    )
    assert at.multiselect(key="available_pokemon").value == []
    assert at.button(key="import_btn")
    assert at.button(key="load_team_json")
    assert at.button(key="load_workspace_json")
    assert any(info.value == "Pick at least one Pokémon to start." for info in at.info)


def test_team_summary_shows_existing_analysis_findings():
    at = run_app_with_team("garchomp,tyranitar")

    assert not at.exception

    markdown_values = [element.value for element in at.markdown]

    assert "### What to review" in markdown_values
    assert any(
        value.startswith("- Shared weaknesses:")
        and "Fairy (2 members: Garchomp, Tyranitar)" in value
        for value in markdown_values
    )
    assert any(
        value.startswith("- 4× weaknesses:")
        and "Garchomp to Ice" in value
        and "Tyranitar to Fighting" in value
        for value in markdown_values
    )
    assert any(value.startswith("- Native-type coverage gaps:") for value in markdown_values)
    assert any(
        "not a battle simulation or an overall team rating" in caption.value
        for caption in at.caption
    )


def test_team_summary_updates_after_direct_team_edit():
    at = run_app_with_team("garchomp,tyranitar")
    at.multiselect(key="team").set_value(["garchomp"]).run()

    assert not at.exception

    markdown_values = [element.value for element in at.markdown]

    assert (
        "- Shared weaknesses: no attack type hits two or more analyzed members super-effectively."
    ) in markdown_values
    assert any(
        value.startswith("- 4× weaknesses:")
        and "Garchomp to Ice" in value
        and "Tyranitar" not in value
        for value in markdown_values
    )


@pytest.mark.parametrize(
    "failed_names",
    [
        pytest.param({"garchomp"}, id="partial-stat-failure"),
        pytest.param(
            {"garchomp", "tyranitar"},
            id="all-stat-lookups-fail",
        ),
    ],
)
def test_stat_failures_preserve_type_analysis(monkeypatch, failed_names):
    attempted_names = []

    def lookup_stats(name, cache):
        attempted_names.append(name)
        if name in failed_names:
            raise requests.ConnectionError("offline")
        return FAKE_STATS

    def unexpected_stat_check(stats):
        raise AssertionError("Team-wide checks must not use incomplete stats")

    def unexpected_loadouts(*args, **kwargs):
        raise AssertionError("Loadouts must not use incomplete stats")

    monkeypatch.setattr(fetch, "stats_cache_first", lookup_stats)
    monkeypatch.setattr(analysis, "stat_warnings", unexpected_stat_check)
    monkeypatch.setattr(
        loadout_ui,
        "render_loadout_suggestions",
        unexpected_loadouts,
    )
    st.cache_data.clear()

    at = run_app_with_team("garchomp,tyranitar")

    assert not at.exception
    assert attempted_names == ["garchomp", "tyranitar"]
    assert at.multiselect(key="team").value == ["garchomp", "tyranitar"]
    assert len(at.tabs) == 7
    assert len(at.metric) >= 5
    assert any(element.value == "### What to review" for element in at.markdown)
    assert any(
        "Couldn't load base stats for:" in warning.value
        and "Type-based analysis remains available." in warning.value
        for warning in at.warning
    )

    moves_tab = at.tabs[2]
    assert moves_tab.multiselect(key="moves_garchomp")
    assert moves_tab.multiselect(key="moves_tyranitar")
    assert any("Suggested move loadouts are unavailable" in info.value for info in moves_tab.info)

    stats_tab = at.tabs[5]
    if len(failed_names) == 1:
        assert len(stats_tab.dataframe) == 1
        assert list(stats_tab.dataframe[0].value.index) == ["tyranitar"]
        assert any(
            "Partial base-stat table: 1 of 2 analyzed members loaded." in warning.value
            for warning in stats_tab.warning
        )
    else:
        assert len(stats_tab.dataframe) == 0
        assert any(
            "Base stats are unavailable for all analyzed members." in info.value
            for info in stats_tab.info
        )

    assert not stats_tab.success
    assert "Suggested move loadouts" not in [header.value for header in at.subheader]


def test_stat_features_recover_without_losing_selected_moves(monkeypatch):
    at = run_app_with_team("garchomp,tyranitar")
    at.multiselect(key="moves_garchomp").set_value(["earthquake"]).run()
    at.multiselect(key="moves_tyranitar").set_value(["ice-beam"]).run()

    team_before = list(at.multiselect(key="team").value)

    def unavailable_stats(name, cache):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(fetch, "stats_cache_first", unavailable_stats)
    st.cache_data.clear()
    at.run()

    assert not at.exception
    assert at.multiselect(key="team").value == team_before
    assert at.multiselect(key="moves_garchomp").value == ["earthquake"]
    assert at.multiselect(key="moves_tyranitar").value == ["ice-beam"]
    assert "Suggested move loadouts" not in [header.value for header in at.subheader]

    monkeypatch.setattr(
        fetch,
        "stats_cache_first",
        lambda name, cache: FAKE_STATS,
    )
    st.cache_data.clear()
    at.run()

    assert not at.exception
    assert at.multiselect(key="team").value == team_before
    assert at.multiselect(key="moves_garchomp").value == ["earthquake"]
    assert at.multiselect(key="moves_tyranitar").value == ["ice-beam"]
    assert "Suggested move loadouts" in [header.value for header in at.subheader]

    stats_tab = at.tabs[5]
    assert len(stats_tab.dataframe) == 1
    assert list(stats_tab.dataframe[0].value.index) == [
        "garchomp",
        "tyranitar",
    ]
    assert not any("Couldn't load base stats for:" in warning.value for warning in at.warning)
    assert not any(
        "Suggested move loadouts are unavailable" in info.value for info in at.tabs[2].info
    )


def test_partial_team_blocks_swap_rankings_and_clears_preview(monkeypatch):
    at = run_app_with_team("garchomp,tyranitar")
    at.multiselect(key="opponent_team").set_value(["dragonite"]).run()

    assert not at.exception

    at.session_state["pending_swap"] = ("garchomp", "ferrothorn")

    def lookup_types(name, cache):
        if name == "tyranitar":
            raise requests.ConnectionError("offline")
        return FAKE_TYPES[name]

    def unexpected_ranking(*args, **kwargs):
        raise AssertionError("Swap ranking must not run for an incomplete team")

    monkeypatch.setattr(fetch, "types_cache_first", lookup_types)
    monkeypatch.setattr(analysis, "suggest_swaps", unexpected_ranking)
    monkeypatch.setattr(analysis, "suggest_matchup_swaps", unexpected_ranking)
    st.cache_data.clear()
    at.run()

    assert not at.exception
    assert at.multiselect(key="team").value == ["garchomp", "tyranitar"]
    assert len(at.tabs) == 7

    best_swap = next(metric for metric in at.metric if metric.label == "Best swap")
    assert best_swap.value == "Unavailable"

    with pytest.raises(KeyError):
        at.session_state["pending_swap"]

    button_keys = [button.key for button in at.button if button.key]
    assert "confirm_swap_preview" not in button_keys
    assert not any(key.startswith("swap_") for key in button_keys)
    assert not any(key.startswith("matchup_swap_") for key in button_keys)

    assert any(
        "Swap suggestions and applying swaps are unavailable" in info.value
        for info in at.tabs[3].info
    )
    assert any(
        "Swap suggestions and applying swaps are unavailable" in info.value
        for info in at.tabs[6].info
    )


def test_swap_confirmation_rechecks_types_before_changing_build(monkeypatch):
    failed_names = set()

    def lookup_types(name, cache):
        if name in failed_names:
            raise requests.ConnectionError("offline")
        return FAKE_TYPES[name]

    monkeypatch.setattr(fetch, "types_cache_first", lookup_types)
    st.cache_data.clear()

    at = run_app_with_team("garchomp,tyranitar")
    at.multiselect(key="locked_members").set_value(["tyranitar"]).run()
    at.multiselect(key="moves_garchomp").set_value(["earthquake"]).run()
    at.multiselect(key="moves_tyranitar").set_value(["ice-beam"]).run()

    assert not at.exception

    swap_buttons = [button for button in at.button if button.key and button.key.startswith("swap_")]
    assert swap_buttons, "Expected an eligible swap for the fixture team"

    swap_buttons[0].click().run()

    assert not at.exception
    assert at.button(key="confirm_swap_preview")

    team_before = list(at.multiselect(key="team").value)
    locks_before = list(at.multiselect(key="locked_members").value)
    raw_url_before = at.query_params["team"]
    url_before = raw_url_before if isinstance(raw_url_before, str) else ",".join(raw_url_before)
    with pytest.raises(KeyError):
        at.session_state["team_before_swap"]

    with pytest.raises(KeyError):
        at.session_state["last_swap"]

    failed_names.add("tyranitar")
    st.cache_data.clear()

    at.button(key="confirm_swap_preview").click().run()

    assert not at.exception
    assert at.multiselect(key="team").value == team_before
    assert at.multiselect(key="locked_members").value == locks_before
    assert at.multiselect(key="moves_garchomp").value == ["earthquake"]
    raw_url_after = at.query_params["team"]
    url_after = raw_url_after if isinstance(raw_url_after, str) else ",".join(raw_url_after)
    assert url_after == url_before

    with pytest.raises(KeyError):
        at.session_state["team_before_swap"]

    with pytest.raises(KeyError):
        at.session_state["last_swap"]

    with pytest.raises(KeyError):
        at.session_state["pending_swap"]

    assert any(
        "Swap suggestions and applying swaps are unavailable" in warning.value
        for warning in at.warning
    )
