from io import BytesIO
from pathlib import Path

import pytest
import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

import pokedex.fetch as fetch
import pokedex.move_ui as move_ui
from pokedex import threat_ui
from pokedex.team_files import dump_team, load_team
from pokedex.team_state import TeamMember, TeamState

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
