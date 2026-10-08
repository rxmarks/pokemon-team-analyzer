from collections.abc import Callable, Mapping, MutableMapping
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

    st.caption(f"{len(chosen)} of {MAX_MOVES} moves selected")

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


STAT_BAR_SCALE = 300
STAT_LABELS: tuple[tuple[str, str], ...] = (
    ("hp", "HP"),
    ("attack", "Attack"),
    ("defense", "Defense"),
    ("special-attack", "Special Attack"),
    ("special-defense", "Special Defense"),
    ("speed", "Speed"),
)


def render_member_stats(name: str, stats: Mapping[str, int] | None) -> None:
    """Display supplied base stats without fetching data or changing team state."""
    with st.expander(f"Base stats — {display_name(name)}"):
        if not stats:
            st.info(
                f"Stats couldn't be loaded for {display_name(name)}. "
                "Types and moves remain available."
            )
            return

        for key, label in STAT_LABELS:
            value = stats.get(key)
            if value is None:
                st.caption(f"{label}: unavailable")
                continue
            fraction = min(max(value, 0), STAT_BAR_SCALE) / STAT_BAR_SCALE
            st.progress(fraction, text=f"{label}: {value}")

        st.caption(
            "Base stats, not calculated battle stats. "
            "All bars share a 0–300 display scale; bar lengths are capped at 300."
        )
        with st.expander("What these stats mean"):
            st.markdown(
                "- HP: the base stat used to calculate health.\n"
                "- Attack / Special Attack: strengths used by physical / special attacks.\n"
                "- Defense / Special Defense: defenses against physical / special attacks.\n"
                "- Speed: helps determine who acts first; other battle effects can change this."
            )


def render_move_coverage(
    team: Team,
    type_chart: TypeChart,
    *,
    sprite_lookup: Callable[[str], str | None] | None = None,
    team_stats: Mapping[str, Mapping[str, int]] | None = None,
) -> None:
    """Render member cards, then team-wide selected-move coverage."""
    st.subheader("Team")
    st.caption(
        "Add up to four moves per member, or leave them empty for now. "
        "Your Pokémon’s types are analyzed either way."
    )

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
                    portrait, identity = st.columns([1, 3])
                    with portrait:
                        if sprite_lookup is not None:
                            sprite = sprite_lookup(name)
                            if sprite:
                                st.image(sprite, width=64)
                    with identity:
                        st.markdown(f"**{display_name(name)}**")
                        st.markdown(type_badges(team[name]), unsafe_allow_html=True)
                        st.caption("Kept on team" if name in locks else "Available for replacement")
                    render_member_stats(name, (team_stats or {}).get(name))
                    team_moves[name] = render_member_move_editor(name, move_cache)

    with st.expander("Coverage from selected moves"):
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
            st.info("Add moves to see which types your team can hit super-effectively.")
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
            st.markdown("Your selected moves do not yet cover these types super-effectively:")
            st.markdown(type_badges(sorted(gaps)), unsafe_allow_html=True)
            st.caption("This is a type-coverage check, not a prediction of a battle result.")
        else:
            st.success("Your moves hit every type super-effectively.")
