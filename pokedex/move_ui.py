from collections.abc import MutableMapping
from typing import Any, cast

import requests
import streamlit as st

from pokedex.analysis import move_coverage_gaps
from pokedex.config import CACHE_TTL_SECONDS, MAX_MOVES
from pokedex.fetch import get_learnable_moves, load_move_cache
from pokedex.team_session import reconcile_team
from pokedex.types import MoveCache, Team, TypeChart


@st.cache_data
def cached_move_cache() -> MoveCache:
    return load_move_cache()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_learnable_moves(name: str) -> list[str]:
    return get_learnable_moves(name)


def pretty(move: str) -> str:
    return move.replace("-", " ").title()


def moves_changed() -> None:
    """Update the structured snapshot after a move selection changes."""
    state = cast(MutableMapping[str, Any], st.session_state)
    reconcile_team(state)


def render_move_coverage(team: Team, type_chart: TypeChart) -> None:
    st.subheader("Move-based coverage")
    st.caption(
        "Pick up to 4 moves per Pokémon. Status moves are preserved but do not "
        "contribute to offensive coverage. Learnsets are not format-legality checks."
    )

    move_cache = cached_move_cache()
    team_moves: dict[str, list[str]] = {}

    for name in team:
        key = f"moves_{name}"
        selected = list(st.session_state.get(key, []))

        try:
            learnable = cached_learnable_moves(name)
        except requests.RequestException:
            learnable = []
            st.warning(
                f"Couldn't load moves for {pretty(name)} from PokeAPI. "
                "Existing selections are preserved but cannot be verified."
            )
        else:
            unverified = [move for move in selected if move not in learnable]
            if unverified:
                st.warning(
                    f"Selected moves for {pretty(name)} were not found in the "
                    "available learnset: "
                    + ", ".join(pretty(move) for move in unverified)
                    + ". They are preserved; check the intended format separately."
                )

        options = sorted(set(learnable) | set(selected))

        team_moves[name] = st.multiselect(
            pretty(name),
            options=options,
            max_selections=MAX_MOVES,
            format_func=pretty,
            key=key,
            on_change=moves_changed,
        )

    unknown_moves = sorted(
        {move for moves in team_moves.values() for move in moves if move not in move_cache}
    )
    if unknown_moves:
        st.warning(
            "Coverage data is unavailable for these selected moves: "
            + ", ".join(pretty(move) for move in unknown_moves)
            + ". They are preserved but excluded from coverage calculations."
        )

    if not any(team_moves.values()):
        st.info("Pick some moves to see move-based coverage gaps.")
        return

    has_known_damaging_move = any(
        move_cache.get(move, {}).get("damage_class") in {"physical", "special"}
        for moves in team_moves.values()
        for move in moves
    )

    if not has_known_damaging_move:
        st.info(
            "No known damaging moves are selected. Status and unknown moves "
            "do not contribute to offensive coverage."
        )
        return

    gaps = move_coverage_gaps(team_moves, move_cache, type_chart)

    if gaps:
        st.warning(
            "Your moves can't hit these types super-effectively: "
            + ", ".join(sorted(type_name.title() for type_name in gaps))
        )
    else:
        st.success("Your moves hit every type super-effectively.")
