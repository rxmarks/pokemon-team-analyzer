from collections.abc import Callable, MutableMapping
from typing import Any, cast

import requests
import streamlit as st

from pokedex.analysis import move_coverage_gaps
from pokedex.config import CACHE_TTL_SECONDS, MAX_MOVES
from pokedex.display import display_name, type_badges
from pokedex.fetch import get_learnable_moves, load_move_cache
from pokedex.move_details import selected_move_details
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
    """Refresh the build and dismiss previews after a manual move edit."""
    state = cast(MutableMapping[str, Any], st.session_state)
    state.pop("pending_loadout", None)
    state.pop("loadout_notice", None)
    state.pop("pending_swap", None)
    state.pop("pending_swap_opponents", None)
    reconcile_team(state)


def render_member_move_editor(name: str, move_cache: MoveCache) -> list[str]:
    """Render one editor while preserving selected and unverified moves."""
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

    chosen = st.multiselect(
        "Selected moves",
        options=options,
        max_selections=MAX_MOVES,
        format_func=pretty,
        key=key,
        on_change=moves_changed,
    )

    st.caption(f"{len(chosen)}/{MAX_MOVES} moves selected")

    if chosen:
        with st.expander(f"Move details — {display_name(name)}"):
            st.dataframe(
                selected_move_details(chosen, move_cache),
                width="stretch",
                hide_index=True,
                column_config={
                    "Move": st.column_config.TextColumn("Move"),
                    "Type": st.column_config.TextColumn("Type"),
                    "Category": st.column_config.TextColumn("Category"),
                    "Power": st.column_config.NumberColumn(
                        "Base power",
                        format="%d",
                        help=(
                            "Cached base power, not calculated damage. "
                            "A blank value means no numeric power is available."
                        ),
                    ),
                    "Coverage": st.column_config.TextColumn(
                        "Coverage status",
                        help=(
                            "Whether this move contributes a damaging attack "
                            "type to the app's coverage calculation."
                        ),
                    ),
                },
            )

    return chosen


def render_move_coverage(
    team: Team,
    type_chart: TypeChart,
    *,
    sprite_lookup: Callable[[str], str | None] | None = None,
) -> None:
    """Render member cards, then team-wide selected-move coverage."""
    st.subheader("Team")
    st.caption("Choose up to 4 moves per member. Review suggested changes in Swap suggestions.")

    with st.expander("How move selection and coverage work"):
        st.markdown(
            "- Status moves are preserved but do not contribute to offensive coverage.\n"
            "- Available learnsets are not battle-format legality checks.\n"
            "- Move details use cached metadata; base power is not calculated damage.\n"
            "- Missing power does not necessarily mean coverage data is unavailable.\n"
            "- Coverage describes this app's type calculation, not a guaranteed matchup."
        )

    move_cache = cached_move_cache()
    team_moves: dict[str, list[str]] = {}
    names = list(team)
    columns_per_row = min(3, len(names)) or 1
    locks = set(st.session_state.get("locked_members", []))

    for start in range(0, len(names), columns_per_row):
        columns = st.columns(columns_per_row)
        row_names = names[start : start + columns_per_row]

        for column, name in zip(columns, row_names, strict=False):
            with column:
                with st.container(border=True):
                    if sprite_lookup is not None:
                        sprite = sprite_lookup(name)
                        if sprite:
                            st.image(sprite, width=80)

                    st.markdown(f"**{display_name(name)}**")
                    st.markdown(type_badges(team[name]), unsafe_allow_html=True)
                    if name in locks:
                        st.caption("Locked against replacement")
                    team_moves[name] = render_member_move_editor(name, move_cache)

    st.markdown("#### Selected-move coverage")

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
