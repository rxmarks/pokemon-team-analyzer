import requests
import streamlit as st

from pokedex.analysis import move_coverage_gaps
from pokedex.fetch import get_learnable_moves, load_move_cache


@st.cache_data
def cached_move_cache() -> dict:
    return load_move_cache()


@st.cache_data
def cached_learnable_moves(name: str) -> list[str]:
    return get_learnable_moves(name)


def pretty(move: str) -> str:
    return move.replace("-", " ").title()


def render_move_coverage(team: dict[str, list[str]], type_chart: dict) -> None:
    st.subheader("Move-based coverage")
    st.caption("Pick up to 4 moves per Pokémon. Status moves don't count toward coverage.")

    move_cache = cached_move_cache()
    team_moves = {}
    for name in team:
        try:
            learnable = cached_learnable_moves(name)
        except requests.RequestException:
            st.warning(f"Couldn't load moves for {pretty(name)} from PokeAPI. Try again later.")
            continue
        damaging = [
            m
            for m in learnable
            if move_cache.get(m, {}).get("damage_class") not in (None, "status")
        ]

        team_moves[name] = st.multiselect(
            pretty(name),
            options=damaging,
            max_selections=4,
            format_func=pretty,
            key=f"moves_{name}",
        )

    if not any(team_moves.values()):
        st.info("Pick some moves to see move-based coverage gaps.")
        return

    gaps = move_coverage_gaps(team_moves, move_cache, type_chart)
    if gaps:
        st.warning(
            "Your moves can't hit these types super-effectively: "
            + ", ".join(sorted(t.title() for t in gaps))
        )
    else:
        st.success("Your moves hit every type super-effectively.")
