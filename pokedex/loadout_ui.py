import requests
import streamlit as st

from pokedex.loadout import loadout_coverage, suggest_loadouts
from pokedex.move_ui import cached_learnable_moves, cached_move_cache
from pokedex.types import MoveCache, Team, TypeChart


def render_loadout_suggestions(
    team: Team,
    chart: TypeChart,
    team_stats: dict[str, dict[str, int]],
) -> dict[str, list[str]]:
    """Render suggested moves and return them for export.

    Returns an empty mapping if learnsets cannot be fetched from PokeAPI.
    """
    st.subheader("Suggested move loadouts")
    try:
        with st.spinner("Building move loadouts..."):
            learnsets = {name: cached_learnable_moves(name) for name in team}
            move_cache: MoveCache = cached_move_cache()
            loadouts = suggest_loadouts(team, learnsets, team_stats, move_cache, chart)
    except requests.RequestException:
        st.error("Couldn't load learnable moves from PokeAPI. Try again in a moment.")
        return {}

    rows = [
        {
            "Pokémon": name.replace("-", " ").title(),
            "Moves": ", ".join(move.replace("-", " ").title() for move in moves)
            or "No eligible moves",
        }
        for name, moves in loadouts.items()
    ]
    st.dataframe(rows, width="stretch", hide_index=True)

    covered = loadout_coverage(loadouts, move_cache, chart)
    st.metric("Types hit super-effectively", f"{len(covered)}/18")
    st.caption(
        "Coverage-optimized, not full competitive sets: ignores status moves, "
        "abilities, items, and Tera."
    )

    with st.expander("How loadouts are picked"):
        st.markdown(
            "Each Pokémon gets its strongest STAB move first. Remaining slots go to "
            "moves that hit new types super-effectively, then to power and the "
            "Pokémon's better attacking stat. Weak (<60 power), status, and "
            "drawback moves like Hyper Beam are skipped."
        )

    return loadouts
