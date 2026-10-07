from collections.abc import MutableMapping
from typing import Any, cast

import requests
import streamlit as st

from pokedex.loadout import loadout_coverage, suggest_loadouts
from pokedex.loadout_session import (
    MoveProposal,
    apply_loadout,
    cancel_loadout,
    loadout_is_current,
    stage_loadout,
)
from pokedex.move_ui import cached_learnable_moves, cached_move_cache, pretty
from pokedex.types import MoveCache, Team, TypeChart


def preview_suggested_moves(species: str, moves: list[str]) -> None:
    """Stage a member's suggestions without changing selected moves."""
    state = cast(MutableMapping[str, Any], st.session_state)
    state.pop("loadout_notice", None)

    try:
        stage_loadout(state, species, moves)
    except ValueError as exc:
        state["loadout_notice"] = str(exc)


def confirm_suggested_moves() -> None:
    """Apply only the targeted member's moves through the shared helper."""
    state = cast(MutableMapping[str, Any], st.session_state)

    if apply_loadout(state):
        state["loadout_notice"] = "Suggested moves applied to the selected Pokémon."
    else:
        state["loadout_notice"] = (
            "The move preview is no longer current. Preview the suggestions again."
        )


def cancel_suggested_moves() -> None:
    """Dismiss the proposal without changing the build."""
    state = cast(MutableMapping[str, Any], st.session_state)
    cancel_loadout(state)
    state.pop("loadout_notice", None)


def _move_list(moves: tuple[str, ...]) -> str:
    return ", ".join(pretty(move) for move in moves) or "None"


def render_loadout_preview() -> None:
    """Keep an existing preview usable even if suggestion lookup fails."""
    state = cast(MutableMapping[str, Any], st.session_state)
    proposal = state.get("pending_loadout")

    if not isinstance(proposal, MoveProposal):
        if proposal is not None:
            cancel_loadout(state)
        return

    if not loadout_is_current(state, proposal):
        cancel_loadout(state)
        st.info("The move preview was dismissed because the member or moves changed.")
        return

    st.subheader(f"Move preview: {pretty(proposal.species)}")
    st.write("Current moves: " + _move_list(proposal.previous_moves))
    st.write("Suggested moves: " + _move_list(proposal.proposed_moves))

    removed = tuple(move for move in proposal.previous_moves if move not in proposal.proposed_moves)
    added = tuple(move for move in proposal.proposed_moves if move not in proposal.previous_moves)

    st.write("Removed: " + _move_list(removed))
    st.write("Added: " + _move_list(added))
    st.caption(
        "Applying replaces this Pokémon's selected moves only. "
        "Suggestions optimize coverage; they are not legality checks. "
        "Species-swap undo still restores the complete pre-swap build, "
        "including its older move selections."
    )

    apply_col, cancel_col = st.columns(2)

    with apply_col:
        st.button(
            "Apply suggested moves",
            key="confirm_loadout",
            on_click=confirm_suggested_moves,
            type="primary",
        )

    with cancel_col:
        st.button(
            "Cancel move preview",
            key="cancel_loadout",
            on_click=cancel_suggested_moves,
        )


def render_loadout_suggestions(
    team: Team,
    chart: TypeChart,
    team_stats: dict[str, dict[str, int]],
) -> dict[str, list[str]]:
    """Render suggested moves and explicit per-member preview controls."""
    st.subheader("Suggested move loadouts")
    render_loadout_preview()

    if notice := st.session_state.get("loadout_notice"):
        st.info(notice)

    try:
        with st.spinner("Building move loadouts..."):
            learnsets = {name: cached_learnable_moves(name) for name in team}
            move_cache: MoveCache = cached_move_cache()
            loadouts = suggest_loadouts(
                team,
                learnsets,
                team_stats,
                move_cache,
                chart,
            )
    except requests.RequestException:
        st.error("Couldn't load learnable moves from PokeAPI. Try again in a moment.")
        return {}

    rows = [
        {
            "Pokémon": pretty(name),
            "Moves": ", ".join(pretty(move) for move in moves) or "No eligible moves",
        }
        for name, moves in loadouts.items()
    ]
    st.dataframe(rows, width="stretch", hide_index=True)

    covered = loadout_coverage(loadouts, move_cache, chart)
    st.metric("Types hit super-effectively", f"{len(covered)}/{len(chart)}")
    st.caption(
        "Coverage-optimized, not full competitive sets: ignores status moves, "
        "abilities, items, and Tera."
    )

    for name, suggested_moves in loadouts.items():
        selected_moves = list(st.session_state.get(f"moves_{name}", []))

        st.button(
            f"Preview suggested moves for {pretty(name)}",
            key=f"preview_loadout_{name}",
            on_click=preview_suggested_moves,
            args=(name, list(suggested_moves)),
            disabled=(not suggested_moves or suggested_moves == selected_moves),
            help=(
                "Review before replacing this member's selected moves. "
                "Disabled when no moves are suggested or selections already match."
            ),
        )

    with st.expander("How loadouts are picked"):
        st.markdown(
            "Each Pokémon gets its strongest STAB move first. Remaining slots go to "
            "moves that hit new types super-effectively, then to power and the "
            "Pokémon's better attacking stat. Weak (<60 power), status, and "
            "drawback moves like Hyper Beam are skipped."
        )

    return loadouts
