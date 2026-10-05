import requests
import streamlit as st

from pokedex.loadout import loadout_coverage, suggest_loadouts
from pokedex.move_ui import cached_learnable_moves, cached_move_cache
from pokedex.types import Team, TypeChart


def render_loadout_suggestions(
    team: Team, chart: TypeChart, team_stats: dict[str, dict[str, int]]
) -> None:
    st.subheader("Suggested move loadouts")
    try:
        with st.spinner("Building move loadouts..."):
            learnsets = {n: cached_learnable_moves(n) for n in team}
            move_cache = cached_move_cache()
            loadouts = suggest_loadouts(team, learnsets, team_stats, move_cache, chart)
    except requests.RequestException:
        st.error("Couldn't load learnable moves from PokeAPI. Try again in a moment.")
        return

    rows = [
        {
            "Pokémon": n.replace("-", " ").title(),
            "Moves": ", ".join(m.replace("-", " ").title() for m in moves) or "No eligible moves",
        }
        for n, moves in loadouts.items()
    ]
    st.dataframe(rows, width="stretch", hide_index=True)

    covered = loadout_coverage(loadouts, move_cache, chart)
    st.metric("Types hit super-effectively", f"{len(covered)}/{len(chart)}")
    st.caption(
        "Coverage-optimized, not full competitive sets: ignores status moves, abilities, and items."
    )

    with st.expander("How loadouts are picked"):
        st.markdown(
            "Each Pokémon gets its strongest STAB move first. Remaining slots go to "
            "moves that hit new types super-effectively, then to power and the "
            "Pokémon's better attacking stat. Weak (<60 power), status, and "
            "drawback moves like Hyper Beam are skipped."
        )
