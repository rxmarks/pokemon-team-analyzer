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
from pokedex.config import (
    CACHE_TTL_SECONDS,
    DEFAULT_TEAM,
    MAX_TEAM_SIZE,
    MIN_BST,
)
from pokedex.display import color_multiplier, display_name, format_multiplier, type_badges
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
from pokedex.showdown import parse_showdown
from pokedex.team_files import dump_team, load_team
from pokedex.team_session import reconcile_team, restore_team, snapshot_team
from pokedex.team_state import TeamMember, TeamState
from pokedex.threat_ui import cached_pokemon, render_meta_threats
from pokedex.types import Team, TypeChart

st.set_page_config(page_title="Pokémon Team Analyzer", page_icon="🔴", layout="wide")

SWAP_OUT = "replaces"
SWAP_IN = "candidate"
SWAP_GAIN = "improvement"
SWAP_BUTTONS = 5


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
st.caption("Type-coverage analysis and swap suggestions. Data from PokeAPI.")

with st.sidebar:
    st.header("About")
    st.markdown(
        "Analyzes a Pokémon team's type matchups and suggests swaps.\n\n"
        "- **Defense:** damage multipliers per attack type\n"
        "- **Offense:** types your team can't hit super-effectively\n"
        "- **Moves:** coverage from actual moves, plus suggested loadouts\n"
        "- **Opponent matchups:** compare against a chosen opponent team\n"
        "- **Meta threats:** matchups vs. top Smogon usage\n"
        "- **Stats:** role and speed checks\n"
        "- **Swaps:** lock members, preview replacements, apply, and undo\n\n"
        "**Data:** [PokeAPI](https://pokeapi.co) · "
        "[Smogon usage stats](https://www.smogon.com/stats/)\n\n"
        "[GitHub repo](https://github.com/rxmarks/pokemon-team-analyzer)"
    )
    st.caption(
        "Type-based matchup rankings; no battle simulation. "
        "The Moves tab separately analyzes selected move coverage."
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
    st.session_state.pop("pending_swap", None)
    reconcile_team(st.session_state)


def locks_changed() -> None:
    """Refresh the snapshot and dismiss a preview when locks change."""
    st.session_state.pop("pending_swap", None)
    reconcile_team(st.session_state)


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


def apply_swap(out_name: str, in_name: str) -> None:
    """Apply a valid replacement and preserve the complete previous build."""
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


def stage_swap(out_name: str, in_name: str) -> None:
    """Stage a valid replacement of an unlocked member."""
    current_team = list(st.session_state["team"])
    locks = set(st.session_state.get("locked_members", []))

    if out_name not in current_team or in_name in current_team or out_name in locks:
        return

    st.session_state["pending_swap"] = (out_name, in_name)


def cancel_swap_preview() -> None:
    """Dismiss the proposed swap without changing the team."""
    st.session_state.pop("pending_swap", None)


def confirm_swap_preview() -> None:
    """Apply the staged swap through the shared undo-aware callback."""
    pending_swap = st.session_state.pop("pending_swap", None)

    if pending_swap is not None:
        apply_swap(*pending_swap)


def undo_swap() -> None:
    """Restore species, moves, and locks from before the last swap."""
    st.session_state.pop("pending_swap", None)
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

if "opponent_team" not in st.session_state:
    st.session_state["opponent_team"] = []

if "locked_members" not in st.session_state:
    st.session_state["locked_members"] = []

reconcile_team(st.session_state)

names = st.multiselect(
    "Pick up to 6 Pokémon (type to search)",
    options=all_names,
    max_selections=MAX_TEAM_SIZE,
    key="team",
    format_func=display_name,
    on_change=clear_swap_history,
)

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

if "team_before_swap" in st.session_state:
    out_name, in_name = st.session_state["last_swap"]
    st.caption(f"Last swap: {display_name(out_name)} → {display_name(in_name)}")
    st.button(
        "Undo last swap",
        key="undo_swap",
        on_click=undo_swap,
        help="Restore your team before the most recent swap.",
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

if names:
    st.query_params["team"] = ",".join(names)
    st.caption("The page URL now links to this team. Copy it to share.")
else:
    st.query_params.pop("team", None)

if not names:
    st.info("Pick at least one Pokémon to start.")
    st.stop()

chart = cached_chart()

with st.spinner("Fetching Pokémon data..."):
    team = load_team_types(names, "your team")

if not team:
    st.error("Couldn't load any Pokémon for your team. Try again in a moment.")
    st.stop()

locked_members = set(st.session_state["locked_members"])
all_members_locked = bool(team) and set(team) <= locked_members

st.subheader("Team")
cols = st.columns(MAX_TEAM_SIZE)

for col, (name, types) in zip(cols, team.items(), strict=False):
    with col:
        sprite = cached_sprite(name)
        if sprite:
            st.image(sprite, width=96)

        st.markdown(f"**{display_name(name)}**")
        st.markdown(type_badges(types), unsafe_allow_html=True)

        if name in locked_members:
            st.caption("Locked")

st.download_button(
    "Download Showdown team",
    data=showdown_export(team),
    file_name="pokemon-team.txt",
    mime="text/plain",
    help="Download this team's Pokémon names in Pokémon Showdown import format.",
)

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
            st.write("Proposed team: " + ", ".join(display_name(name) for name in proposed_team))

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

table = team_table(team, chart)
member_cols = list(team)
gaps = coverage_gaps(team, chart)

try:
    with st.spinner("Fetching base stats..."):
        team_stats = {name: cached_stats(name) for name in team}
except requests.RequestException:
    st.error("Couldn't load base stats from PokeAPI. Try again in a moment.")
    st.stop()

candidates = cached_candidates()
if not candidates:
    st.error("No candidates loaded. Check that data/pokemon.json exists and isn't empty.")
    st.stop()

with st.spinner("Ranking swap candidates..."):
    swaps = suggest_swaps(
        team,
        candidates,
        chart,
        locked_members=locked_members,
    )

shared_weak = int(((table[member_cols] >= 2).sum(axis=1) >= 2).sum())
quad_weak = int((table[member_cols] >= 4).to_numpy().sum())
best_swap = f"−{swaps[SWAP_GAIN].iloc[0]:g}" if not swaps.empty else "None"

m1, m2, m3, m4, m5 = st.columns(5)

m1.metric(
    "Team badness",
    team_badness(team, chart),
    help="Problem types + coverage gaps. Lower is better.",
)
m2.metric(
    "Shared weaknesses",
    shared_weak,
    help="Attack types that hit 2+ members super-effectively.",
)
m3.metric(
    "Coverage gaps",
    len(gaps),
    help="Types no member's type hits super-effectively.",
)
m4.metric(
    "4x weaknesses",
    quad_weak,
    help="Member/type pairs taking quadruple damage.",
)
m5.metric(
    "Best swap",
    best_swap,
    help="Badness drop from the top-ranked eligible single swap.",
)

defense, offense, moves, opponent_matchups, threats, stats_tab, swaps_tab = st.tabs(
    [
        "Defense",
        "Offense",
        "Moves",
        "Opponent matchups",
        "Meta threats",
        "Stats",
        "Swaps",
    ]
)

with defense:
    styled = (
        table.style.map(color_multiplier, subset=member_cols)
        .format(format_multiplier, subset=member_cols)
        .format("{:g}", subset=["# weak", "# resist", "total"])
    )
    st.dataframe(styled, width="stretch")
    st.caption(
        "▲▲ = 4× weak · ▲ = 2× weak · ▼ = resists · ▼▼ = double resist · ✕ = immune. Colors match."
    )

    with st.expander("How to read this table"):
        st.markdown(
            "Each row is an attack type and each column is one of your Pokémon. "
            "Cells show the damage multiplier: 4 and 2 mean weak, 0.5 and 0.25 mean "
            "resists, 0 means immune. 'total' sums the row across your team."
        )

with offense:
    if gaps:
        st.warning("No super-effective coverage against these types:")
        st.markdown(type_badges(sorted(gaps)), unsafe_allow_html=True)
    else:
        st.success("Your team's types hit every type super-effectively.")

    with st.expander("How to read coverage gaps"):
        st.markdown(
            "This checks only your Pokémon's own types (STAB). A gap means no "
            "team member's type is super-effective against that type. The Moves "
            "tab accounts for actual moves."
        )

with moves:
    render_move_coverage(team, chart)
    render_loadout_suggestions(team, chart, team_stats)

with opponent_matchups:
    st.subheader("Opponent Matchups")
    st.caption("Compare your team's type-based pressure against up to six opposing Pokémon.")

    opponent_names = st.multiselect(
        "Pick up to 6 opposing Pokémon",
        options=all_names,
        max_selections=MAX_TEAM_SIZE,
        key="opponent_team",
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
                value=True,
                key="matchup_improvements_only",
                help=(
                    "Compare each proposed team with your current team using "
                    "the ranking priorities. Uncheck to include equal or worse alternatives."
                ),
            )

            eligible_candidates = any(name not in team for name in candidates)

            with st.spinner("Ranking matchup-specific swaps..."):
                matchup_swaps = cached_matchup_swaps(
                    team,
                    candidates,
                    opponent_team,
                    chart,
                    improvements_only=improvements_only,
                    locked_members=frozenset(locked_members),
                )

            if all_members_locked:
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
                        args=(out_name, in_name),
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

with threats:
    render_meta_threats(team, chart)

with stats_tab:
    st.dataframe(pd.DataFrame(team_stats).T, width="stretch")

    warnings = stat_warnings(team_stats)
    if warnings:
        for warning in warnings:
            st.warning(warning)
    else:
        st.success("Team has speed, physical, and special attackers covered.")

    with st.expander("How to read the stat check"):
        st.markdown(
            "Rows are your Pokémon and columns are base stats. Warnings flag a "
            "team that lacks fast members, or leans entirely physical or special."
        )

with swaps_tab:
    st.caption(f"Searching {len(candidates)} Pokémon with base stat total {MIN_BST}+.")

    if all_members_locked:
        st.info("All team members are locked. Unlock one to see swap suggestions.")
    elif swaps.empty:
        st.info("No eligible single swaps are available.")
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
                    f"(−{gain:g} badness)"
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
