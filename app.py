import pandas as pd
import requests
import streamlit as st

from pokedex.analysis import (
    coverage_gaps,
    matchup_table,
    opponent_threat_report,
    stat_warnings,
    suggest_matchup_swaps,
    suggest_swaps,
    team_badness,
    team_table,
)
from pokedex.analysis_safety import has_complete_team
from pokedex.config import (
    CACHE_TTL_SECONDS,
    DEFAULT_TEAM,
    MAX_TEAM_SIZE,
    MIN_BST,
)
from pokedex.display import (
    color_multiplier,
    display_name,
    format_badness_change,
    format_multiplier,
    type_badges,
)
from pokedex.export import showdown_export
from pokedex.fetch import (
    get_all_pokemon_names,
    get_sprite,
    load_type_chart,
    stats_cache_first,
    types_cache_first,
)
from pokedex.loadout_ui import render_loadout_suggestions
from pokedex.move_ui import render_move_coverage
from pokedex.pool_import import PoolImportPreview, parse_pool_import
from pokedex.showdown import parse_showdown
from pokedex.swap_explanation import compare_type_analysis
from pokedex.swap_explanation_ui import render_swap_explanation
from pokedex.team_files import dump_team, load_team
from pokedex.team_session import reconcile_team, restore_team, snapshot_team
from pokedex.team_state import TeamMember, TeamState
from pokedex.team_summary import summarize_team
from pokedex.team_summary_ui import render_team_summary
from pokedex.threat_ui import cached_pokemon, render_meta_threats
from pokedex.types import Team, TypeChart
from pokedex.workspace_files import dump_workspace, load_workspace
from pokedex.workspace_session import restore_workspace, snapshot_workspace

st.set_page_config(page_title="Pokémon Team Analyzer", page_icon="🔴", layout="wide")

SWAP_OUT = "replaces"
SWAP_IN = "candidate"
SWAP_GAIN = "improvement"
SWAP_BUTTONS = 5

PARTIAL_OPPONENT_SWAP_MESSAGE = (
    "Matchup-specific swap suggestions are unavailable until types "
    "can be loaded for every selected opponent. "
    "Overall team swaps remain available when your own team is fully loaded."
)

PARTIAL_TEAM_SWAP_MESSAGE = (
    "Swap suggestions and applying swaps are unavailable until types "
    "can be loaded for every selected team member. "
    "Available analysis covers loaded members only."
)


@st.cache_data
def cached_chart() -> TypeChart:
    return load_type_chart()


@st.cache_data(
    ttl=CACHE_TTL_SECONDS,
    max_entries=64,
    show_spinner=False,
)
def cached_matchup_swaps(
    team: Team,
    candidates: Team,
    opponent_team: Team,
    chart: TypeChart,
    improvements_only: bool = False,
    locked_members: frozenset[str] = frozenset(),
) -> pd.DataFrame:
    return suggest_matchup_swaps(
        team,
        candidates,
        opponent_team,
        chart,
        improvements_only=improvements_only,
        locked_members=set(locked_members),
    )


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_types(name: str) -> list[str]:
    return types_cache_first(name, cached_pokemon())


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_names() -> list[str]:
    return get_all_pokemon_names()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_stats(name: str) -> dict[str, int]:
    return stats_cache_first(name, cached_pokemon())


@st.cache_data
def cached_candidates() -> Team:
    return {
        name: data["types"]
        for name, data in cached_pokemon().items()
        if sum(data["stats"].values()) >= MIN_BST
        and not any(tag in name for tag in ("-gmax", "-totem"))
    }


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_sprite(name: str) -> str | None:
    try:
        return get_sprite(name)
    except requests.RequestException:
        return None


st.title("Pokémon Team Analyzer")
st.caption(
    "Build a Pokémon team, explore its strengths and weaknesses, and compare possible changes."
)

with st.sidebar:
    st.header("About")
    st.markdown(
        "Analyzes a Pokémon team's type matchups and suggests swaps.\n\n"
        "- **Team builder:** choose members and moves; inspect stats and coverage\n"
        "- **Swap suggestions:** preview move loadouts and Pokémon replacements\n"
        "- **Opponent matchups:** compare teams and inspect matchup replacements\n"
        "- **Meta threats:** a separate Smogon dataset within Opponent matchups\n\n"
        "**Data:** [PokeAPI](https://pokeapi.co) · "
        "[Smogon usage stats](https://www.smogon.com/stats/)\n\n"
        "[GitHub repo](https://github.com/rxmarks/pokemon-team-analyzer)"
    )
    st.caption(
        "Type-based matchup rankings; no battle simulation. "
        "Team builder separately analyzes selected-move coverage."
    )

try:
    all_names = cached_names()
except requests.RequestException:
    all_names = sorted(cached_pokemon())
    st.warning("PokeAPI is unreachable, so only locally cached Pokémon are available.")


def team_from_url(valid: list[str]) -> list[str]:
    raw = st.query_params.get("team")
    if not raw:
        return list(DEFAULT_TEAM)

    valid_set = set(valid)
    picked = [name.strip().lower() for name in raw.split(",")]
    cleaned = list(dict.fromkeys(name for name in picked if name in valid_set))
    return cleaned[:MAX_TEAM_SIZE] or list(DEFAULT_TEAM)


def clear_swap_history() -> None:
    """Invalidate undo and preview after a direct team edit or import."""
    st.session_state.pop("team_before_swap", None)
    st.session_state.pop("last_swap", None)
    st.session_state.pop("pending_loadout", None)
    st.session_state.pop("loadout_notice", None)
    st.session_state.pop("pending_swap", None)
    st.session_state.pop("pending_swap_opponents", None)
    reconcile_team(st.session_state)


def opponent_selection_changed() -> None:
    """Dismiss only previews that depend on opponent selection."""
    if st.session_state.get("pending_swap_opponents") is not None:
        cancel_swap_preview()


def replacement_options_changed() -> None:
    """Dismiss a preview without changing the team or its undo history."""
    st.session_state.pop("pending_swap", None)
    st.session_state.pop("pending_swap_opponents", None)


def pool_import_preview() -> PoolImportPreview:
    """Parse the current bulk input without changing the pool."""
    input_format = (
        "showdown" if st.session_state.get("pool_input_format") == "Showdown roster" else "names"
    )

    return parse_pool_import(
        st.session_state.get("pool_paste", ""),
        all_names,
        input_format=input_format,
    )


def pool_import_input_changed() -> None:
    """Dismiss old feedback without changing the pool or swap state."""
    st.session_state.pop("pool_import_message", None)


def apply_pool_import(replace: bool) -> None:
    """Apply recognized species without changing the team build."""
    preview = pool_import_preview()

    if not preview.recognized:
        return

    previous = list(st.session_state.get("available_pokemon", []))

    if replace:
        updated = list(preview.recognized)
    else:
        updated = list(dict.fromkeys([*previous, *preview.recognized]))

    st.session_state["available_pokemon"] = updated
    st.session_state["candidate_source"] = "My available Pokémon"
    replacement_options_changed()

    if replace:
        message = f"Replaced the pool with {len(updated)} Pokémon."
    else:
        added_count = len(updated) - len(previous)
        message = f"Added {added_count} new Pokémon. The pool now contains {len(updated)} Pokémon."

    st.session_state["pool_import_message"] = message


def locks_changed() -> None:
    """Refresh the snapshot and dismiss a preview when locks change."""
    st.session_state.pop("pending_swap", None)
    st.session_state.pop("pending_swap_opponents", None)
    reconcile_team(st.session_state)


def import_workspace_json(contents: bytes | None) -> None:
    """Validate the whole workspace before replacing session state."""
    if contents is None:
        st.session_state["workspace_file_error"] = "Choose a workspace JSON file first."
        st.session_state.pop("workspace_file_success", None)
        return

    try:
        imported = load_workspace(
            contents,
            valid_species=set(all_names),
        )
    except ValueError as exc:
        st.session_state["workspace_file_error"] = str(exc)
        st.session_state.pop("workspace_file_success", None)
        return

    restore_workspace(st.session_state, imported)
    st.session_state["workspace_file_success"] = "Workspace loaded."


def import_team_json(contents: bytes | None) -> None:
    """Validate a saved team before replacing any supported build state."""
    if contents is None:
        st.session_state["team_file_error"] = "Choose a JSON team file first."
        st.session_state.pop("team_file_success", None)
        return

    try:
        imported = load_team(contents, valid_species=set(all_names))
    except ValueError as exc:
        st.session_state["team_file_error"] = str(exc)
        st.session_state.pop("team_file_success", None)
        return

    restore_team(st.session_state, imported)
    clear_swap_history()

    for key in ("import_ok", "import_skipped", "import_notes"):
        st.session_state.pop(key, None)

    st.session_state.pop("team_file_error", None)
    st.session_state["team_file_success"] = "Saved team loaded."


def import_showdown() -> None:
    """Import supported species and moves without losing retained locks."""
    mons = parse_showdown(st.session_state.get("showdown_paste", ""))
    valid = set(all_names)
    previous_locks = set(st.session_state.get("locked_members", []))

    st.session_state["import_skipped"] = [mon.species for mon in mons if mon.species not in valid]
    st.session_state["import_notes"] = []

    members: list[TeamMember] = []
    seen_species: set[str] = set()

    for mon in mons:
        if mon.species not in valid:
            continue

        if mon.species in seen_species:
            st.session_state["import_notes"].append(
                f"Skipped duplicate species: {display_name(mon.species)}."
            )
            continue

        seen_species.add(mon.species)
        moves = tuple(dict.fromkeys(mon.moves))

        if len(moves) != len(mon.moves):
            st.session_state["import_notes"].append(
                f"Removed duplicate move entries for {display_name(mon.species)}."
            )

        members.append(
            TeamMember(
                species=mon.species,
                moves=moves,
                locked=mon.species in previous_locks,
            )
        )

    st.session_state["import_ok"] = bool(members)

    if members:
        imported = TeamState(members=tuple(members))
        restore_team(st.session_state, imported)
        clear_swap_history()


def matchup_context_is_available(expected_opponents: tuple[str, ...]) -> bool:
    """Require unchanged opponent selection and complete opponent type data."""
    selected = tuple(st.session_state.get("opponent_team", []))

    if selected != expected_opponents:
        return False

    loaded: list[str] = []

    for name in selected:
        try:
            types = cached_types(name)
        except requests.RequestException:
            continue

        if types:
            loaded.append(name)

    return has_complete_team(selected, loaded)


def swap_team_is_available() -> bool:
    """Recheck selected-team types before staging or applying a swap."""
    selected = list(st.session_state.get("team", []))
    loaded: list[str] = []

    for name in selected:
        try:
            types = cached_types(name)
        except requests.RequestException:
            continue

        if types:
            loaded.append(name)

    complete = has_complete_team(selected, loaded)

    if not complete:
        st.session_state.pop("pending_swap", None)
        st.session_state.pop("pending_swap_opponents", None)
        st.session_state["swap_safety_notice"] = PARTIAL_TEAM_SWAP_MESSAGE

    return complete


def apply_swap(out_name: str, in_name: str) -> None:
    """Apply a valid replacement and preserve the complete previous build."""
    if not swap_team_is_available():
        return
    opponent_context = st.session_state.get("pending_swap_opponents")

    if opponent_context is not None:
        if not matchup_context_is_available(opponent_context):
            cancel_swap_preview()
            st.session_state["swap_safety_notice"] = (
                "The matchup-derived swap was not applied because "
                "the opponent selection changed or opponent types could not "
                "be fully loaded. Review the opponent team and preview again."
            )
            return
    current = snapshot_team(st.session_state)

    if (
        out_name not in current.species
        or in_name in current.species
        or out_name in current.locked_members
    ):
        return

    proposed = TeamState(
        members=tuple(
            TeamMember(species=in_name) if member.species == out_name else member
            for member in current.members
        )
    )

    st.session_state["team_before_swap"] = current
    st.session_state["last_swap"] = (out_name, in_name)
    restore_team(st.session_state, proposed)


def stage_swap(
    out_name: str,
    in_name: str,
    opponent_context: tuple[str, ...] | None = None,
) -> None:
    """Stage a replacement, optionally tied to a selected opponent team."""
    if not swap_team_is_available():
        return

    if opponent_context is not None:
        if not matchup_context_is_available(opponent_context):
            cancel_swap_preview()
            st.session_state["swap_safety_notice"] = (
                "This matchup recommendation is unavailable because "
                "the opponent selection changed or opponent types could not "
                "be fully loaded. Review the opponent team and preview again."
            )
            return

    current_team = list(st.session_state["team"])
    locks = set(st.session_state.get("locked_members", []))

    if out_name not in current_team or in_name in current_team or out_name in locks:
        return

    st.session_state["pending_swap"] = (out_name, in_name)

    if opponent_context is None:
        st.session_state.pop("pending_swap_opponents", None)
    else:
        st.session_state["pending_swap_opponents"] = opponent_context


def cancel_swap_preview() -> None:
    """Dismiss the proposed swap and its opponent context."""
    st.session_state.pop("pending_swap", None)
    st.session_state.pop("pending_swap_opponents", None)


def confirm_swap_preview() -> None:
    """Validate and apply the staged swap before clearing its context."""
    pending_swap = st.session_state.get("pending_swap")
    pending_opponents = st.session_state.get("pending_swap_opponents")
    if pending_opponents is not None and pending_opponents is not None:
        if not matchup_context_is_available(pending_opponents):
            cancel_swap_preview()
            st.session_state["swap_safety_notice"] = (
                "The matchup-derived swap was not applied because "
                "the opponent selection changed or opponent types could not "
                "be fully loaded. Review the opponent team and preview again."
            )
            return
    if pending_swap is not None:
        apply_swap(*pending_swap)

    cancel_swap_preview()


def undo_swap() -> None:
    """Restore species, moves, and locks from before the last swap."""
    st.session_state.pop("pending_swap", None)
    st.session_state.pop("pending_swap_opponents", None)
    previous = st.session_state.pop("team_before_swap", None)

    if previous is not None:
        restore_team(st.session_state, previous)

    st.session_state.pop("last_swap", None)


def load_team_types(names: list[str], error_context: str) -> Team:
    """Fetch selected Pokémon types and show a friendly warning on failure."""
    selected_team: Team = {}

    for name in names:
        try:
            selected_team[name] = cached_types(name)
        except requests.RequestException:
            st.warning(
                f"Couldn't load '{display_name(name)}' for {error_context}. Try again in a moment."
            )

    return selected_team


if "team" not in st.session_state:
    st.session_state["team"] = team_from_url(all_names)

# Preserve these preferences even when their widgets are not rendered.
st.session_state["opponent_team"] = st.session_state.get("opponent_team", [])
st.session_state["matchup_improvements_only"] = st.session_state.get(
    "matchup_improvements_only",
    True,
)

if "locked_members" not in st.session_state:
    st.session_state["locked_members"] = []

reconcile_team(st.session_state)

team_builder, swap_suggestions, opponent_matchups = st.tabs(
    ["Team builder", "Swap suggestions", "Opponent matchups"]
)

with team_builder:
    st.subheader("Build your team")
    st.caption(
        "Choose up to six Pokémon to start. Moves are optional: "
        "add them for a more detailed coverage check. "
        "You can also import a team from a saved file or Showdown."
    )

    names = st.multiselect(
        "Pick up to 6 Pokémon (type to search)",
        options=all_names,
        max_selections=MAX_TEAM_SIZE,
        key="team",
        format_func=display_name,
        on_change=clear_swap_history,
    )

    selected_lock_count = len(st.session_state.get("locked_members", []))

    st.caption(
        f"Team: {len(names)}/{MAX_TEAM_SIZE} Pokémon selected · "
        f"{selected_lock_count} locked against replacement"
    )

    if "team_before_swap" in st.session_state:
        out_name, in_name = st.session_state["last_swap"]
        st.caption(f"Last swap: {display_name(out_name)} → {display_name(in_name)}")
        st.button(
            "Undo last swap",
            key="undo_swap",
            on_click=undo_swap,
            help="Restore your team before the most recent swap.",
        )

with swap_suggestions:
    with st.expander("Replacement options"):
        st.multiselect(
            "Keep these Pokémon on the team",
            options=names,
            key="locked_members",
            format_func=display_name,
            on_change=locks_changed,
            help=(
                "Locked Pokémon still contribute to analysis, but neither swap engine "
                "can recommend replacing them."
            ),
        )
        candidate_source = st.radio(
            "Which Pokémon can be suggested as replacements?",
            options=["Current recommendation pool", "My available Pokémon"],
            key="candidate_source",
            on_change=replacement_options_changed,
        )

        available_pokemon = st.multiselect(
            "My available Pokémon",
            options=all_names,
            key="available_pokemon",
            format_func=display_name,
            on_change=replacement_options_changed,
            help=(
                "Choose Pokémon you own, can obtain, or want to consider. "
                "This limits replacements only; it does not change your team."
            ),
        )

        if candidate_source == "My available Pokémon":
            st.caption(
                f"{len(available_pokemon)} Pokémon selected. "
                "Your selected pool is not filtered by base-stat total or form tags. "
                "Availability and battle legality are not verified."
            )
        else:
            st.caption(
                f"Using locally cached candidates with base stat total {MIN_BST}+. "
                "Gigantamax and Totem forms are excluded. "
                "Your available-Pokémon selections are retained but not applied."
            )

        st.caption(
            "This pool limits suggested replacements; it does not change your current team. "
            "Save a workspace to keep the pool and replacement settings. "
            "Team JSON saves only your team build."
        )
        st.markdown("#### Paste a replacement list")

        st.radio(
            "Input format",
            options=["Pokémon names", "Showdown roster"],
            key="pool_input_format",
            on_change=pool_import_input_changed,
            horizontal=True,
        )

        st.text_area(
            "Paste Pokémon names or a Showdown roster",
            key="pool_paste",
            height=120,
            on_change=pool_import_input_changed,
            help=(
                "Names mode accepts comma-separated names or one name per line. "
                "Showdown mode extracts species and ignores build details. "
                "Nothing changes until you click Add to pool or Replace pool."
            ),
        )

        pool_preview = pool_import_preview()

        if st.session_state.get("pool_paste", "").strip():
            st.caption(
                f"{len(pool_preview.recognized)} recognized species · "
                f"{len(pool_preview.duplicates)} repeated species · "
                f"{len(pool_preview.unrecognized)} unrecognized entries"
            )

            if pool_preview.recognized:
                st.write(
                    "Recognized: "
                    + ", ".join(display_name(name) for name in pool_preview.recognized)
                )
            else:
                st.warning("No recognized Pokémon were found. Your pool is unchanged.")

            if pool_preview.duplicates:
                st.caption(
                    "Repeated species will be included once: "
                    + ", ".join(display_name(name) for name in pool_preview.duplicates)
                )

            if pool_preview.unrecognized:
                st.warning(
                    "These entries will not be imported: " + ", ".join(pool_preview.unrecognized)
                )

        add_col, replace_col = st.columns(2)

        with add_col:
            st.button(
                "Add to pool",
                key="pool_add",
                on_click=apply_pool_import,
                args=(False,),
                disabled=not pool_preview.recognized,
                help="Keep existing pool selections and append recognized species.",
            )

        with replace_col:
            st.button(
                "Replace pool",
                key="pool_replace",
                on_click=apply_pool_import,
                args=(True,),
                disabled=not pool_preview.recognized,
                help="Replace all pool selections with the recognized preview.",
            )

        st.caption(
            "Both actions use recognized species only and activate "
            "My available Pokémon. Unrecognized entries are excluded."
        )

        if message := st.session_state.get("pool_import_message"):
            st.success(message)

with team_builder:
    with st.expander("Import / export / saved files"):
        st.caption(
            "Showdown text: species and moves · "
            "Team JSON: supported team build and locks · "
            "Workspace JSON: team, replacement pool, opponents, and settings"
        )
        with st.expander("Import from Pokémon Showdown"):
            st.text_area(
                "Paste a team export (Teambuilder → Import/Export)",
                key="showdown_paste",
                height=200,
            )
            st.button("Import team", key="import_btn", on_click=import_showdown)

            if "import_ok" in st.session_state:
                if st.session_state["import_ok"]:
                    st.success("Team imported.")
                else:
                    st.error("Couldn't find any Pokémon in that paste.")

                skipped = st.session_state.get("import_skipped")
                if skipped:
                    st.warning("Skipped (not found in PokeAPI): " + ", ".join(skipped))

                for note in st.session_state.get("import_notes", []):
                    st.warning(note)

                if st.session_state["import_ok"]:
                    st.caption(
                        "Imported species and moves only. Items, abilities, EVs, IVs, "
                        "and other build details are not imported yet."
                    )

        with st.expander("Save or load team JSON"):
            st.caption(
                "Saves your main team's species, order, selected moves, and locks. "
                "Does not save opponents, items, abilities, EVs, IVs, or format settings. "
                "Move selections are preserved, not checked for battle legality."
            )

            st.download_button(
                "Download team JSON",
                data=dump_team(snapshot_team(st.session_state)),
                file_name="pokemon-team.json",
                mime="application/json",
                key="download_team_json",
                on_click="ignore",
            )

            uploaded_team = st.file_uploader(
                "Choose a saved JSON team",
                type=["json"],
                key="team_json_upload",
                help="Selecting a file does not replace your team. Click Load team to apply it.",
            )

            uploaded_contents = uploaded_team.getvalue() if uploaded_team is not None else None

            st.button(
                "Load team",
                key="load_team_json",
                on_click=import_team_json,
                args=(uploaded_contents,),
                disabled=uploaded_contents is None,
                help="Replace your main team after the entire file passes validation.",
            )

            if error := st.session_state.get("team_file_error"):
                st.error(error)

            if success := st.session_state.get("team_file_success"):
                st.success(success)

        with st.expander("Save or load workspace"):
            st.caption(
                "Save your supported team build, available-Pokémon pool, "
                "replacement source, opponents, and matchup filter. "
                "Use team JSON when you only want to save a team."
            )
            st.caption(
                "Workspace files do not include swap history, paste text, "
                "items, abilities, EVs, IVs, or battle-format rules. "
                "This is a manual file save, not automatic persistence."
            )

            try:
                workspace_contents = dump_workspace(snapshot_workspace(st.session_state))
            except ValueError as exc:
                st.warning(f"Couldn't prepare workspace download: {exc}")
            else:
                st.download_button(
                    "Download workspace JSON",
                    data=workspace_contents,
                    file_name="pokemon-workspace.json",
                    mime="application/json",
                    key="download_workspace_json",
                    on_click="ignore",
                )

            uploaded_workspace = st.file_uploader(
                "Choose a saved workspace JSON",
                type=["json"],
                key="workspace_json_upload",
                help=(
                    "Selecting a file changes nothing. Load workspace replaces "
                    "the team, pool, opponents, and saved settings after validation."
                ),
            )

            workspace_upload_contents = (
                uploaded_workspace.getvalue() if uploaded_workspace is not None else None
            )

            st.button(
                "Load workspace",
                key="load_workspace_json",
                on_click=import_workspace_json,
                args=(workspace_upload_contents,),
                disabled=workspace_upload_contents is None,
                help=(
                    "Successful loading clears swap preview, undo history, and old import feedback."
                ),
            )

            if error := st.session_state.get("workspace_file_error"):
                st.error(error)

            if success := st.session_state.get("workspace_file_success"):
                st.success(success)

        st.download_button(
            "Download Showdown team",
            data=showdown_export(snapshot_team(st.session_state)),
            file_name="pokemon-team.txt",
            mime="text/plain",
            key="download_showdown",
            on_click="ignore",
            disabled=not names,
            help=(
                "Export the selected team's species and current selected moves. "
                "Does not export items, abilities, EVs, IVs, natures, or locks."
            ),
        )

        st.caption(
            "Showdown export includes species and selected moves only. "
            "Unverified move selections are preserved; names, forms, and battle "
            "legality are not validated for your target format. "
            "Use team or workspace JSON to preserve locks."
        )

if names:
    st.query_params["team"] = ",".join(names)
    st.caption(
        "Copy the page URL to share species only. "
        "Use a downloaded file to share selected moves or saved settings."
    )
else:
    st.query_params.pop("team", None)

if not names:
    st.info("Pick at least one Pokémon to start.")
    st.stop()

chart = cached_chart()

with st.spinner("Fetching Pokémon data..."):
    team = load_team_types(names, "your team")

team_complete = has_complete_team(names, team)

if not team_complete:
    cancel_swap_preview()

if notice := st.session_state.pop("swap_safety_notice", None):
    st.warning(notice)

if not team:
    st.error("Couldn't load any Pokémon for your team. Try again in a moment.")
    st.stop()

locked_members = set(st.session_state["locked_members"])
all_members_locked = bool(team) and set(team) <= locked_members


table = team_table(team, chart)
member_cols = list(team)
gaps = coverage_gaps(team, chart)

team_stats: dict[str, dict[str, int]] = {}
missing_stats: list[str] = []

with st.spinner("Fetching base stats..."):
    for name in team:
        try:
            team_stats[name] = cached_stats(name)
        except requests.RequestException:
            missing_stats.append(name)

team_stats_complete = not missing_stats

if missing_stats:
    missing_names = ", ".join(display_name(name) for name in missing_stats)
    st.warning(
        f"Couldn't load base stats for: {missing_names}. "
        "Type-based analysis remains available. "
        "Stat checks and suggested move loadouts require stats "
        "for every analyzed member."
    )

if candidate_source == "My available Pokémon":
    replacement_names = [name for name in available_pokemon if name not in names]

    with st.spinner("Loading available replacement Pokémon..."):
        candidates = load_team_types(
            replacement_names,
            "your available replacement pool",
        )

    if not available_pokemon:
        st.warning(
            "Choose Pokémon in Replacement options to receive swap suggestions. "
            "Your current team analysis is still available."
        )
else:
    candidates = cached_candidates()

    if not candidates:
        st.warning(
            "The current recommendation pool is empty. "
            "Choose My available Pokémon in Replacement options, "
            "or check the local Pokémon cache."
        )

eligible_replacement_count = sum(name not in team for name in candidates)

swaps = pd.DataFrame()

if team_complete:
    with st.spinner("Ranking swap candidates..."):
        swaps = suggest_swaps(
            team,
            candidates,
            chart,
            locked_members=locked_members,
        )

shared_weak = int(((table[member_cols] >= 2).sum(axis=1) >= 2).sum())
quad_weak = int((table[member_cols] >= 4).to_numpy().sum())
if not team_complete:
    best_swap = "Unavailable"
else:
    best_swap = (
        format_badness_change(float(swaps[SWAP_GAIN].iloc[0])) if not swaps.empty else "None"
    )

with team_builder:
    render_move_coverage(
        team,
        chart,
        sprite_lookup=cached_sprite,
        team_stats=team_stats,
    )

    summary = summarize_team(team, table, gaps)

    render_team_summary(
        summary,
        selected_count=len(names),
        analyzed_count=len(team),
    )

    with st.expander("Type-balance details"):
        m1, m2, m3, m4, m5 = st.columns(5)

        m1.metric(
            "Type-balance score",
            team_badness(team, chart),
            help="Counts type-based concerns and coverage gaps. Lower is better.",
        )
        m2.metric(
            "Shared weaknesses",
            shared_weak,
            help="Attack types that hit 2+ members super-effectively.",
        )
        m3.metric(
            "Types to cover",
            len(gaps),
            help="Types no member's type hits super-effectively.",
        )
        m4.metric(
            "4× weaknesses",
            quad_weak,
            help="Member/type pairs taking quadruple damage.",
        )
        m5.metric(
            "Best swap",
            best_swap,
            help=(
                "Change in team badness for the top-ranked eligible single swap. "
                "Negative means lower badness; positive means higher badness; "
                "zero means unchanged badness."
            ),
        )
        st.caption(
            "Lower is better. This score counts type-based concerns; "
            "it is not a rating of battle performance."
        )

    with st.expander("Team roles"):
        st.caption(
            "These checks look for fast members and physical or special attackers. "
            "They use base stats, not training, items, abilities, or selected moves."
        )

        if not team_stats_complete:
            if team_stats:
                st.warning(
                    f"Partial base-stat table: {len(team_stats)} of "
                    f"{len(team)} analyzed members loaded. "
                    "Team-wide speed and attacker-role checks are unavailable."
                )
            else:
                st.info(
                    "Base stats are unavailable for all analyzed members. "
                    "Team-wide speed and attacker-role checks are unavailable."
                )
        else:
            warnings = stat_warnings(team_stats)
            if warnings:
                for warning in warnings:
                    st.warning(warning)
            else:
                st.success("Team has speed, physical, and special attackers covered.")

    with st.expander("Compare all base stats"):
        st.caption(
            "An optional side-by-side reference. "
            "You can also inspect base stats inside each Pokémon's card."
        )

        if team_stats:
            st.dataframe(pd.DataFrame(team_stats).T, width="stretch")
        else:
            st.info("No base stats are available to compare.")

    st.markdown("### Coverage details")
    with st.expander("Defensive coverage"):
        styled = (
            table.style.map(color_multiplier, subset=member_cols)
            .format(format_multiplier, subset=member_cols)
            .format("{:g}", subset=["# weak", "# resist", "total"])
        )
        st.dataframe(styled, width="stretch")
        st.caption(
            "▲▲ = 4× weak · ▲ = 2× weak · ▼ = resists · "
            "▼▼ = double resist · ✕ = immune. Colors match."
        )

        with st.expander("How to read this table"):
            st.markdown(
                "Each row is an attack type and each column is one of your Pokémon. "
                "Cells show the damage multiplier: 4 and 2 mean weak, 0.5 and 0.25 mean "
                "resists, 0 means immune. 'total' sums the row across your team."
            )

    with st.expander("Coverage from your Pokémon’s types"):
        if gaps:
            st.warning("No super-effective coverage against these types:")
            st.markdown(type_badges(sorted(gaps)), unsafe_allow_html=True)
        else:
            st.success("Your team's types hit every type super-effectively.")

        with st.expander("How to read coverage gaps"):
            st.markdown(
                "This checks only your Pokémon's own types (STAB). "
                "A gap means no team member's type is super-effective "
                "against that type. Selected-move coverage accounts "
                "for actual moves."
            )

with swap_suggestions:
    st.markdown("### Move changes")
    if team_stats_complete:
        render_loadout_suggestions(team, chart, team_stats)
    else:
        st.info(
            "Suggested move loadouts are unavailable until base stats "
            "can be loaded for every analyzed member. "
            "Selected-move coverage remains available."
        )

    st.markdown("### Pokémon replacements")
    st.caption(
        f"Replacement pool: {eligible_replacement_count} eligible Pokémon "
        f"from {candidate_source.lower()}."
    )
    if not team_complete:
        st.info(PARTIAL_TEAM_SWAP_MESSAGE)
    elif all_members_locked:
        st.info("All team members are locked. Unlock one to see swap suggestions.")
    elif eligible_replacement_count == 0:
        st.info("No eligible single swaps are available.")
    elif swaps.empty:
        st.info("No swap suggestions were produced for the selected replacements.")
    else:
        shown = swaps.copy()
        shown.insert(0, "sprite", [cached_sprite(name) for name in shown[SWAP_IN]])

        st.dataframe(
            shown,
            width="stretch",
            hide_index=True,
            column_config={
                "sprite": st.column_config.ImageColumn("", width="small"),
                SWAP_IN: st.column_config.TextColumn("Swap in"),
                SWAP_OUT: st.column_config.TextColumn("Swap out"),
                "new_badness": st.column_config.NumberColumn(
                    "New badness",
                    help="Lower is better.",
                ),
                SWAP_GAIN: st.column_config.NumberColumn(
                    "Improvement",
                    help="Badness drop vs. current team. Negative values mean worse badness.",
                ),
                "weak_total": st.column_config.NumberColumn(
                    "Weakness total",
                    help="Number of weak attack-type/member pairs. Lower is better.",
                ),
            },
        )

        st.markdown("**Try a swap**")

        for index, row in enumerate(swaps.head(SWAP_BUTTONS).itertuples(index=False)):
            out_name = getattr(row, SWAP_OUT)
            in_name = getattr(row, SWAP_IN)
            gain = getattr(row, SWAP_GAIN)

            st.button(
                (
                    f"Preview: {display_name(out_name)} → {display_name(in_name)} "
                    f"({format_badness_change(float(gain))} badness change)"
                ),
                key=f"swap_{index}",
                on_click=stage_swap,
                args=(out_name, in_name),
            )

        st.caption(
            "Preview a replacement before applying it. Applying updates your team, "
            "the URL, and every tab; Undo restores the previous team."
        )

    with st.expander("How to read swap suggestions"):
        st.markdown(
            "Each row proposes replacing an unlocked team member with a candidate. "
            "'New badness' is the team's score after the swap; lower is better. "
            "The table ranks eligible alternatives, which may include non-improvements. "
            "Preview a suggestion, then apply or cancel it. Undo restores the team "
            "before your most recent swap."
        )

with opponent_matchups:
    st.subheader("Opponent Matchups")
    st.caption("Compare your team's type-based pressure against up to six opposing Pokémon.")
    st.caption(
        "Team-member locks apply here too. Manage them in Swap suggestions → Replacement options."
    )
    opponent_names = st.multiselect(
        "Pick up to 6 opposing Pokémon",
        options=all_names,
        max_selections=MAX_TEAM_SIZE,
        key="opponent_team",
        on_change=opponent_selection_changed,
        format_func=display_name,
        help=(
            "Choose an opposing team to see which of your Pokémon have favorable, "
            "even, or risky type matchups."
        ),
    )

    if not opponent_names:
        st.info("Pick at least one opposing Pokémon to analyze matchups.")
    else:
        with st.spinner("Fetching opponent data..."):
            opponent_team = load_team_types(opponent_names, "the opponent team")

        opponent_complete = has_complete_team(opponent_names, opponent_team)

        if not opponent_complete:
            st.warning(
                f"Partial opponent analysis: {len(opponent_team)} of "
                f"{len(opponent_names)} selected opponents loaded. "
                "Matchup results cover loaded opponents only."
            )

        if not opponent_team:
            st.warning("Couldn't load any opposing Pokémon. Try again in a moment.")
        else:
            opponent_cols = st.columns(MAX_TEAM_SIZE)

            for col, (name, types) in zip(
                opponent_cols,
                opponent_team.items(),
                strict=False,
            ):
                with col:
                    sprite = cached_sprite(name)
                    if sprite:
                        st.image(sprite, width=72)

                    st.markdown(f"**{display_name(name)}**")
                    st.markdown(type_badges(types), unsafe_allow_html=True)

            with st.spinner("Calculating matchup analysis..."):
                matchups = matchup_table(team, opponent_team, chart)
                threat_rows = opponent_threat_report(team, opponent_team, chart)

            st.markdown("#### Matchup grid")
            st.dataframe(matchups, width="stretch")

            st.markdown("#### Matchup-specific swap suggestions")
            st.caption(
                "Ranked by lower threat pressure, then higher matchup balance. "
                "Overall team health breaks ties. Locked members cannot be replaced."
            )

            improvements_only = st.checkbox(
                "Show only improvements",
                key="matchup_improvements_only",
                help=(
                    "Compare each proposed team with your current team using "
                    "the ranking priorities. Uncheck to include equal or worse alternatives."
                ),
            )

            eligible_candidates = any(name not in team for name in candidates)

            matchup_swaps = pd.DataFrame()

            if team_complete and opponent_complete:
                with st.spinner("Ranking matchup-specific swaps..."):
                    matchup_swaps = cached_matchup_swaps(
                        team,
                        candidates,
                        opponent_team,
                        chart,
                        improvements_only=improvements_only,
                        locked_members=frozenset(locked_members),
                    )

            if not team_complete:
                st.info(PARTIAL_TEAM_SWAP_MESSAGE)
            elif not opponent_complete:
                st.info(PARTIAL_OPPONENT_SWAP_MESSAGE)
            elif all_members_locked:
                st.info("All team members are locked. Unlock one to see swap suggestions.")
            elif not eligible_candidates:
                st.info("No eligible single swaps are available.")
            elif matchup_swaps.empty:
                st.info(
                    "No beneficial single swap found. Uncheck 'Show only improvements' "
                    "to explore other alternatives."
                )
            else:
                shown_matchup_swaps = matchup_swaps.copy()
                shown_matchup_swaps.insert(
                    0,
                    "sprite",
                    [cached_sprite(name) for name in shown_matchup_swaps[SWAP_IN]],
                )

                st.dataframe(
                    shown_matchup_swaps,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "sprite": st.column_config.ImageColumn("", width="small"),
                        SWAP_IN: st.column_config.TextColumn("Swap in"),
                        SWAP_OUT: st.column_config.TextColumn("Swap out"),
                        "is_improvement": st.column_config.CheckboxColumn(
                            "Improves ranking",
                            help="True when the proposed team ranks above your current team.",
                        ),
                        "threat_pressure": st.column_config.NumberColumn(
                            "Threat pressure",
                            help=(
                                "Threatened members minus super-effective attackers. "
                                "Lower is better."
                            ),
                        ),
                        "matchup_balance": st.column_config.NumberColumn(
                            "Matchup balance",
                            help=(
                                "Total native-type pressure across both teams. Higher is better."
                            ),
                        ),
                        "new_badness": st.column_config.NumberColumn(
                            "New badness",
                            help="Overall team score after the swap. Lower is better.",
                        ),
                        "weak_total": st.column_config.NumberColumn(
                            "Weakness total",
                            help="Number of weak attack-type/member pairs after the swap.",
                        ),
                        "pressure_improvement": st.column_config.NumberColumn(
                            "Pressure improvement",
                            help="Current pressure minus proposed pressure. Positive is better.",
                        ),
                        "balance_improvement": st.column_config.NumberColumn(
                            "Balance improvement",
                            help="Proposed balance minus current balance. Positive is better.",
                        ),
                        "badness_improvement": st.column_config.NumberColumn(
                            "Badness improvement",
                            help="Current badness minus proposed badness. Positive is better.",
                        ),
                        "weakness_improvement": st.column_config.NumberColumn(
                            "Weakness improvement",
                            help=(
                                "Current weakness count minus proposed count. Positive is better."
                            ),
                        ),
                    },
                )

                st.caption(
                    "Positive improvement values are better; negative values show a downside. "
                    "A swap can improve opponent matchups while worsening overall team health."
                )

                current_threats = threat_rows.set_index("opponent")

                for index, row in enumerate(
                    matchup_swaps.head(SWAP_BUTTONS).itertuples(index=False)
                ):
                    out_name = row.replaces
                    in_name = row.candidate
                    swap_label = f"{display_name(out_name)} → {display_name(in_name)}"

                    with st.expander(f"Why this swap? {swap_label}"):
                        if row.pressure_improvement > 0:
                            st.write("Primary benefit: lower opponent threat pressure.")
                        elif row.pressure_improvement < 0:
                            st.write("Downside: higher opponent threat pressure.")
                        elif row.balance_improvement > 0:
                            st.write(
                                "Primary benefit: higher matchup balance, "
                                "with unchanged total threat pressure."
                            )
                        elif row.balance_improvement < 0:
                            st.write("Downside: lower matchup balance.")
                        elif row.badness_improvement > 0:
                            st.write(
                                "Opponent metrics are unchanged; overall team badness improves."
                            )
                        elif row.weakness_improvement > 0:
                            st.write(
                                "Opponent metrics and badness are unchanged; "
                                "the team has fewer weakness pairs."
                            )
                        elif row.is_improvement:
                            st.write("The proposed team improves the ranking.")
                        else:
                            st.write("This alternative does not improve the current ranking.")

                        if row.badness_improvement < 0:
                            st.warning(
                                "Tradeoff: overall team badness increases by "
                                f"{-row.badness_improvement:g}."
                            )
                        if row.weakness_improvement < 0:
                            st.warning(
                                "Tradeoff: weakness pairs increase by "
                                f"{-row.weakness_improvement:g}."
                            )

                        proposed_team = {
                            name: candidates[in_name] if name == out_name else types
                            for name, types in team.items()
                        }
                        proposed_threats = opponent_threat_report(
                            proposed_team,
                            opponent_team,
                            chart,
                        ).set_index("opponent")

                        explanation_rows = []
                        for opponent_name in opponent_team:
                            before = current_threats.loc[opponent_name]
                            after = proposed_threats.loc[opponent_name]

                            explanation_rows.append(
                                {
                                    "Opponent": display_name(opponent_name),
                                    "Threatened before": int(before["threatens"]),
                                    "Threatened after": int(after["threatens"]),
                                    "Attackers before": int(before["answered_by"]),
                                    "Attackers after": int(after["answered_by"]),
                                    "Pressure improvement": (
                                        int(before["threat_score"]) - int(after["threat_score"])
                                    ),
                                }
                            )

                        st.dataframe(
                            pd.DataFrame(explanation_rows),
                            width="stretch",
                            hide_index=True,
                        )
                        st.caption(
                            "'Attackers' means members with super-effective native-type "
                            "offense. It does not mean a safe switch-in or guaranteed win."
                        )

                    st.button(
                        f"Preview: {swap_label}",
                        key=f"matchup_swap_{index}",
                        on_click=stage_swap,
                        args=(out_name, in_name, tuple(opponent_names)),
                    )

            st.markdown("#### Opponent threat report")
            st.dataframe(
                threat_rows,
                width="stretch",
                hide_index=True,
                column_config={
                    "opponent": st.column_config.TextColumn("Opponent"),
                    "threatens": st.column_config.NumberColumn(
                        "Members threatened",
                        help=(
                            "How many of your Pokémon are weak to at least one of "
                            "this opponent's native types."
                        ),
                    ),
                    "answered_by": st.column_config.NumberColumn(
                        "Super-effective attackers",
                        help=(
                            "How many of your Pokémon can hit this opponent "
                            "super-effectively using a native type. This does not "
                            "mean they can safely switch in or win the matchup."
                        ),
                    ),
                    "threat_score": st.column_config.NumberColumn(
                        "Threat score",
                        help=(
                            "Members threatened minus super-effective attackers. "
                            "Higher values are more concerning."
                        ),
                    ),
                    "weak_members": st.column_config.TextColumn("Threatens"),
                    "answers": st.column_config.TextColumn("Super-effective attackers"),
                },
            )

            with st.expander("How to read these matchups"):
                st.markdown(
                    "- **Favorable:** Your Pokémon's best native-type attack is more "
                    "effective against the opponent than the opponent's best "
                    "native-type attack is against yours.\n"
                    "- **Even:** Both Pokémon have equal native-type pressure.\n"
                    "- **Risky:** The opponent has stronger native-type pressure "
                    "against your Pokémon.\n\n"
                    "This is a type-only heuristic. It does not account for "
                    "specific moves, abilities, held items, base stats, Speed, "
                    "Tera types, switching, or competitive battle formats."
                )

preview_container = (
    opponent_matchups
    if st.session_state.get("pending_swap_opponents") is not None
    else swap_suggestions
)

with preview_container:
    pending_swap = st.session_state.get("pending_swap")

    if pending_swap is not None:
        out_name, in_name = pending_swap

        if out_name not in team or in_name in team or out_name in locked_members:
            cancel_swap_preview()
        else:
            st.subheader("Swap preview")
            st.write(f"Replace {display_name(out_name)} with {display_name(in_name)}.")

            try:
                proposed_types = cached_types(in_name)
            except requests.RequestException:
                st.warning(
                    f"Couldn't load {display_name(in_name)} for the preview. "
                    "Cancel or try again shortly."
                )
                st.button(
                    "Cancel preview",
                    key="cancel_swap_preview",
                    on_click=cancel_swap_preview,
                )
            else:
                proposed_team = {
                    name if name != out_name else in_name: (
                        types if name != out_name else proposed_types
                    )
                    for name, types in team.items()
                }

                current_badness = team_badness(team, chart)
                proposed_badness = team_badness(proposed_team, chart)
                current_table = team_table(team, chart)
                proposed_table = team_table(proposed_team, chart)
                current_weaknesses = int(current_table["# weak"].sum())
                proposed_weaknesses = int(proposed_table["# weak"].sum())

                preview_comparison = pd.DataFrame(
                    [
                        {
                            "Metric": "Overall team badness",
                            "Current": current_badness,
                            "Proposed": proposed_badness,
                            "Improvement": current_badness - proposed_badness,
                        },
                        {
                            "Metric": "Weakness pairs",
                            "Current": current_weaknesses,
                            "Proposed": proposed_weaknesses,
                            "Improvement": current_weaknesses - proposed_weaknesses,
                        },
                    ]
                )

                st.dataframe(
                    preview_comparison,
                    width="stretch",
                    hide_index=True,
                )
                st.caption(
                    "Positive improvement values are better. These are overall team "
                    "metrics; opponent-specific tradeoffs appear in the matchup explanations."
                )
                st.write(
                    "Proposed team: " + ", ".join(display_name(name) for name in proposed_team)
                )

                explanation = compare_type_analysis(
                    current_team=team,
                    proposed_team=proposed_team,
                    current_table=current_table,
                    proposed_table=proposed_table,
                    current_gaps=coverage_gaps(team, chart),
                    proposed_gaps=coverage_gaps(proposed_team, chart),
                )
                render_swap_explanation(explanation)
                apply_col, cancel_col = st.columns(2)
                with apply_col:
                    st.button(
                        "Apply swap",
                        key="confirm_swap_preview",
                        on_click=confirm_swap_preview,
                        type="primary",
                    )
                with cancel_col:
                    st.button(
                        "Cancel preview",
                        key="cancel_swap_preview",
                        on_click=cancel_swap_preview,
                    )

with opponent_matchups:
    st.markdown("### Smogon meta threats")
    render_meta_threats(team, chart)
