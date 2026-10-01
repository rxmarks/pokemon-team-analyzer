import requests
import streamlit as st
import pandas as pd

from pokedex.analysis import coverage_gaps, stat_warnings, suggest_swaps, team_badness, team_table
from pokedex.fetch import get_all_pokemon_names, get_stats, get_types, load_type_chart

st.set_page_config(page_title="Pokémon Team Analyzer", layout="wide")

CANDIDATES = [
    "lucario", "metagross", "scizor", "heatran", "magnezone",
    "azumarill", "clefable", "conkeldurr", "excadrill", "empoleon",
    "blissey", "skarmory", "corviknight", "breloom", "infernape",
    "weavile", "gengar", "volcarona", "hydreigon", "rotom-wash",
]
DEFAULT_TEAM = ["dragonite", "gyarados", "garchomp", "ferrothorn", "togekiss", "tyranitar"]


@st.cache_data
def cached_chart() -> dict:
    return load_type_chart()


@st.cache_data
def cached_types(name: str) -> list[str]:
    return get_types(name)


@st.cache_data
def cached_names() -> list[str]:
    return get_all_pokemon_names()

@st.cache_data
def cached_stats(name: str) -> dict[str, int]:
    return get_stats(name)

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

names = st.multiselect(
    "Pick up to 6 Pokémon (type to search)",
    options=cached_names(),
    default=DEFAULT_TEAM,
    max_selections=6,
)

if not names:
    st.info("Pick at least one Pokémon to start.")
    st.stop()

chart = cached_chart()
team = {}
for name in names:
    try:
        team[name] = cached_types(name)
    except requests.HTTPError:
        st.error(f"Couldn't load '{name}' from PokeAPI. Try again in a moment.")
        st.stop()

st.subheader("Team")
st.write(", ".join(f"**{n}** ({' / '.join(t)})" for n, t in team.items()))

st.subheader("Defense: weakness table")
table = team_table(team, chart)
member_cols = list(team)
styled = (
    table.style
    .map(color_multiplier, subset=member_cols)
    .format("{:g}", subset=member_cols + ["total"])
)
st.dataframe(styled, width="stretch")
st.caption("Red = weak (dark red = 4x), green = resists, blue = immune.")

st.subheader("Offense: coverage gaps")
gaps = coverage_gaps(team, chart)
if gaps:
    st.warning("No super-effective coverage against: " + ", ".join(sorted(gaps)))
else:
    st.success("Your team's types hit every type super-effectively.")

st.subheader("Stats: role check")
team_stats = {n: cached_stats(n) for n in team}
st.dataframe(pd.DataFrame(team_stats).T, width="stretch")
warnings = stat_warnings(team_stats)
if warnings:
    for w in warnings:
        st.warning(w)
else:
    st.success("Team has speed, physical, and special attackers covered.")

st.subheader("Swap suggestions")
st.write(f"Current team badness: **{team_badness(team, chart)}** (problem types + coverage gaps, lower is better)")
with st.spinner("Checking candidates..."):
    candidates = {c: cached_types(c) for c in CANDIDATES}
st.dataframe(suggest_swaps(team, candidates, chart), width="stretch", hide_index=True)