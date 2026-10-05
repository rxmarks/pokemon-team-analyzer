import pandas as pd
import requests
import streamlit as st

from pokedex.analysis import (
    coverage_gaps,
    stat_warnings,
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
from pokedex.threat_ui import cached_pokemon, render_meta_threats

st.set_page_config(page_title="Pokémon Team Analyzer", layout="wide")


@st.cache_data
def cached_chart() -> dict:
    return load_type_chart()


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
        name: d["types"]
        for name, d in cached_pokemon().items()
        if sum(d["stats"].values()) >= MIN_BST
        and not any(tag in name for tag in ("-gmax", "-totem"))
    }


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_sprite(name: str) -> str | None:
    try:
        return get_sprite(name)
    except requests.RequestException:
        return None


def color_multiplier(value):
    if value >= 4:
        return "background-color: #b91c1c; color: white"
    if value >= 2:
        return "background-color: #f87171"
    if value == 0:
        return "background-color: #60a5fa"
    if value < 1:
        return "background-color: #86efac"
    return ""


st.title("Pokémon Team Analyzer")
st.caption("Type-coverage analysis and swap suggestions. Data from PokeAPI.")

with st.sidebar:
    st.header("About")
    st.markdown(
        "Analyzes a Pokémon team's type matchups and suggests swaps.\n\n"
        "- **Defense:** damage multipliers per attack type\n"
        "- **Offense:** types your team can't hit super-effectively\n"
        "- **Moves:** coverage from up to 4 actual moves\n"
        "- **Meta threats:** matchups vs. top Smogon usage\n"
        "- **Stats:** role and speed checks\n"
        "- **Suggestions:** swaps that fix the most weaknesses\n\n"
        "**Data:** [PokeAPI](https://pokeapi.co) · "
        "[Smogon usage stats](https://www.smogon.com/stats/)\n\n"
        "[GitHub repo](https://github.com/rxmarks/pokemon-team-analyzer)"
    )
    st.caption("Type-based analysis only; ignores abilities, items, and Tera.")

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
    picked = [n.strip().lower() for n in raw.split(",")]
    cleaned = list(dict.fromkeys(n for n in picked if n in valid_set))
    return cleaned[:MAX_TEAM_SIZE] or DEFAULT_TEAM


def import_showdown() -> None:
    mons = parse_showdown(st.session_state.get("showdown_paste", ""))
    valid = set(all_names)
    found = list(dict.fromkeys(m.species for m in mons if m.species in valid))
    st.session_state["import_skipped"] = [m.species for m in mons if m.species not in valid]
    st.session_state["import_ok"] = bool(found)
    if found:
        st.session_state["team"] = found[:MAX_TEAM_SIZE]


if "team" not in st.session_state:
    st.session_state["team"] = team_from_url(all_names)

names = st.multiselect(
    "Pick up to 6 Pokémon (type to search)",
    options=all_names,
    max_selections=MAX_TEAM_SIZE,
    key="team",
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
team = {}
with st.spinner("Fetching Pokémon data..."):
    for name in names:
        try:
            team[name] = cached_types(name)
        except requests.RequestException:
            st.error(f"Couldn't load '{name}' from PokeAPI. Try again in a moment.")
            st.stop()

st.subheader("Team")
cols = st.columns(MAX_TEAM_SIZE)
for col, (name, types) in zip(cols, team.items(), strict=False):
    with col:
        sprite = cached_sprite(name)
        if sprite:
            st.image(sprite, width=96)
        st.markdown(f"**{name.replace('-', ' ').title()}**")
        st.caption(" / ".join(t.title() for t in types))

st.subheader("Defense: weakness table")
table = team_table(team, chart)
member_cols = list(team)
styled = table.style.map(color_multiplier, subset=member_cols).format(
    "{:g}", subset=member_cols + ["total"]
)
st.dataframe(styled, width="stretch")
st.caption("Red = weak (dark red = 4x), green = resists, blue = immune.")

with st.expander("How to read this table"):
    st.markdown(
        "Each row is an attack type and each column is one of your Pokémon. "
        "Cells show the damage multiplier: 4 and 2 mean weak, 0.5 and 0.25 mean "
        "resists, 0 means immune. 'total' sums the row across your team."
    )

st.subheader("Offense: coverage gaps")
gaps = coverage_gaps(team, chart)
if gaps:
    st.warning("No super-effective coverage against: " + ", ".join(sorted(gaps)))
else:
    st.success("Your team's types hit every type super-effectively.")

with st.expander("How to read coverage gaps"):
    st.markdown(
        "This checks only your Pokémon's own types (STAB). A gap means no "
        "team member's type is super-effective against that type. The move "
        "coverage section below accounts for actual moves."
    )

render_move_coverage(team, chart)
render_meta_threats(team, chart)

st.subheader("Stats: role check")
try:
    with st.spinner("Fetching base stats..."):
        team_stats = {n: cached_stats(n) for n in team}
except requests.RequestException:
    st.error("Couldn't load base stats from PokeAPI. Try again in a moment.")
    st.stop()

st.dataframe(pd.DataFrame(team_stats).T, width="stretch")
warnings = stat_warnings(team_stats)
if warnings:
    for w in warnings:
        st.warning(w)
else:
    st.success("Team has speed, physical, and special attackers covered.")

with st.expander("How to read the stat check"):
    st.markdown(
        "Rows are your Pokémon and columns are base stats. Warnings flag a "
        "team that lacks fast members, or leans entirely physical or special, "
        "which makes it easy to wall."
    )

st.subheader("Swap suggestions")
st.write(
    f"Current team badness: **{team_badness(team, chart)}** "
    "(problem types + coverage gaps, lower is better)"
)

candidates = cached_candidates()
if not candidates:
    st.error("No candidates loaded. Check that data/pokemon.json exists and isn't empty.")
    st.stop()

st.caption(f"Searching {len(candidates)} Pokémon with base stat total {MIN_BST}+.")

with st.spinner("Ranking swap candidates..."):
    swaps = suggest_swaps(team, candidates, chart)
st.dataframe(swaps, width="stretch", hide_index=True)

with st.expander("How to read swap suggestions"):
    st.markdown(
        "Each row replaces one team member with a candidate and shows the new "
        "team badness. Badness counts types that hit 2+ members super-"
        "effectively plus offensive coverage gaps. Lower is better."
    )

render_loadout_suggestions(team, chart, team_stats)
