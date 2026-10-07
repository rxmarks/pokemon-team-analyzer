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
from pokedex.loadout import suggest_loadouts
from pokedex.loadout_ui import render_loadout_suggestions
from pokedex.move_ui import cached_learnable_moves, cached_move_cache, render_move_coverage
from pokedex.showdown import parse_showdown
from pokedex.threat_ui import cached_pokemon, render_meta_threats
from pokedex.types import Team, TypeChart

st.set_page_config(page_title="Pokémon Team Analyzer", page_icon="🔴", layout="wide")


SWAP_OUT = "replaces"
SWAP_IN = "candidate"
SWAP_GAIN = "improvement"
SWAP_BUTTONS = 5


@st.cache_data
def cached_chart() -> dict:
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
) -> pd.DataFrame:
    return suggest_matchup_swaps(
        team,
        candidates,
        opponent_team,
        chart,
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
def cached_candidates() -> dict[str, list[str]]:
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
        "- **Opponent matchups:** compare your team against a chosen opponent team\n"
        "- **Meta threats:** matchups vs. top Smogon usage\n"
        "- **Stats:** role and speed checks\n"
        "- **Swaps:** one-click replacements that fix the most weaknesses\n\n"
        "**Data:** [PokeAPI](https://pokeapi.co) · "
        "[Smogon usage stats](https://www.smogon.com/stats/)\n\n"
        "[GitHub repo](https://github.com/rxmarks/pokemon-team-analyzer)"
    )
    st.caption("Type-based analysis only; ignores abilities, items, moves, and Tera.")


try:
    all_names = cached_names()
except requests.RequestException:
    all_names = sorted(cached_pokemon())
    st.warning("PokeAPI is unreachable, so only locally cached Pokémon are available.")


def team_from_url(valid: list[str]) -> list[str]:
    raw = st.query_params.get("team")
    if not raw:
        return DEFAULT_TEAM

    valid_set = set(valid)
    picked = [name.strip().lower() for name in raw.split(",")]
    cleaned = list(dict.fromkeys(name for name in picked if name in valid_set))
    return cleaned[:MAX_TEAM_SIZE] or DEFAULT_TEAM


def import_showdown() -> None:
    mons = parse_showdown(st.session_state.get("showdown_paste", ""))
    valid = set(all_names)
    found = list(dict.fromkeys(mon.species for mon in mons if mon.species in valid))

    st.session_state["import_skipped"] = [mon.species for mon in mons if mon.species not in valid]
    st.session_state["import_ok"] = bool(found)

    if found:
        st.session_state["team"] = found[:MAX_TEAM_SIZE]


def apply_swap(out_name: str, in_name: str) -> None:
    st.session_state["team"] = [
        in_name if name == out_name else name for name in st.session_state["team"]
    ]


def load_team_types(names: list[str], error_context: str) -> dict[str, list[str]]:
    """Fetch selected Pokémon types and show a friendly error on failure."""
    selected_team: dict[str, list[str]] = {}

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


names = st.multiselect(
    "Pick up to 6 Pokémon (type to search)",
    options=all_names,
    max_selections=MAX_TEAM_SIZE,
    key="team",
    format_func=display_name,
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


st.subheader("Team")
cols = st.columns(MAX_TEAM_SIZE)

for col, (name, types) in zip(cols, team.items(), strict=False):
    with col:
        sprite = cached_sprite(name)
        if sprite:
            st.image(sprite, width=96)

        st.markdown(f"**{display_name(name)}**")
        st.markdown(type_badges(types), unsafe_allow_html=True)


st.download_button(
    "Download Showdown team",
    data=showdown_export(team),
    file_name="pokemon-team.txt",
    mime="text/plain",
    help="Download this team's Pokémon names in Pokémon Showdown import format.",
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
    swaps = suggest_swaps(team, candidates, chart)


try:
    with st.spinner("Building move loadouts..."):
        learnsets = {name: cached_learnable_moves(name) for name in team}
        move_cache = cached_move_cache()
        loadouts = suggest_loadouts(team, learnsets, team_stats, move_cache, chart)
except requests.RequestException:
    loadouts = {}


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
    help="Badness drop from the top-ranked single swap.",
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
                "Ranked for the selected opponent team: lower threat pressure first, "
                "then higher matchup balance. Overall team health breaks ties. "
                "These are type-only rankings, not battle predictions."
            )

            with st.spinner("Ranking matchup-specific swaps..."):
                matchup_swaps = cached_matchup_swaps(
                    team,
                    candidates,
                    opponent_team,
                    chart,
                )

            if matchup_swaps.empty:
                st.info("No eligible single swaps are available.")
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
                        "threat_pressure": st.column_config.NumberColumn(
                            "Threat pressure",
                            help="Threatened members minus offensive answers. Lower is better.",
                        ),
                        "matchup_balance": st.column_config.NumberColumn(
                            "Matchup balance",
                            help="Total native-type pressure across both teams. Higher is better.",
                        ),
                        "pressure_improvement": st.column_config.NumberColumn(
                            "Pressure improvement",
                            help=(
                                "Current pressure minus pressure after the swap. "
                                "Positive is better."
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
                    },
                )

                st.caption(
                    "The table ranks eligible replacements; it does not guarantee "
                    "that every listed swap improves on your current team. "
                    "A positive pressure improvement means fewer net threats."
                )

                st.markdown("**Try a matchup swap**")
                for index, row in enumerate(
                    matchup_swaps.head(SWAP_BUTTONS).itertuples(index=False)
                ):
                    out_name = row.replaces
                    in_name = row.candidate

                    st.button(
                        f"{display_name(out_name)} → {display_name(in_name)}",
                        key=f"matchup_swap_{index}",
                        on_click=apply_swap,
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
                        "Available answers",
                        help=(
                            "How many of your Pokémon can hit this opponent "
                            "super-effectively using one of their native types."
                        ),
                    ),
                    "threat_score": st.column_config.NumberColumn(
                        "Threat score",
                        help=(
                            "Members threatened minus available answers. "
                            "Higher values are more concerning."
                        ),
                    ),
                    "weak_members": st.column_config.TextColumn("Threatens"),
                    "answers": st.column_config.TextColumn("Answered by"),
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
                    "This is a type-only heuristic. It does not yet account for "
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
            "team that lacks fast members, or leans entirely physical or special, "
            "which makes it easy to wall."
        )


with swaps_tab:
    st.caption(f"Searching {len(candidates)} Pokémon with base stat total {MIN_BST}+.")

    if swaps.empty:
        st.success("No single swap improves this team.")
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
                    help="Badness drop vs. current team.",
                ),
                "weak_total": st.column_config.NumberColumn(
                    "Weakness total",
                    help=("Sum of super-effective weaknesses; tiebreaker, lower is better."),
                ),
            },
        )

        st.markdown("**Try a swap**")

        for index, row in enumerate(swaps.head(SWAP_BUTTONS).itertuples(index=False)):
            out_name = getattr(row, SWAP_OUT)
            in_name = getattr(row, SWAP_IN)
            gain = getattr(row, SWAP_GAIN)

            st.button(
                (f"{display_name(out_name)} → {display_name(in_name)} (−{gain:g} badness)"),
                key=f"swap_{index}",
                on_click=apply_swap,
                args=(out_name, in_name),
            )

        st.caption("Applying a swap updates the team, the URL, and every tab.")

    with st.expander("How to read swap suggestions"):
        st.markdown(
            "Each row replaces one team member with a candidate. 'New badness' is "
            "the team's score after the swap, and lower is better. Use the buttons "
            "to try a swap. The URL updates, so you can share the result."
        )
