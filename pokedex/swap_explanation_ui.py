"""Streamlit presentation of before/after type-analysis differences."""

import streamlit as st

from pokedex.display import display_name
from pokedex.swap_explanation import SwapExplanation


def render_swap_explanation(explanation: SwapExplanation) -> None:
    """Explain reductions and tradeoffs without implying battle outcomes."""
    reductions: list[str] = []
    tradeoffs: list[str] = []

    for change in explanation.reduced_shared_weaknesses:
        reductions.append(
            f"Fewer members weak to {change.attack_type.title()}: "
            f"{len(change.before_members)} → {len(change.after_members)}."
        )

    for weakness in explanation.removed_quad_weaknesses:
        reductions.append(
            f"Removes the 4× weakness entry for "
            f"{display_name(weakness.species)} to "
            f"{weakness.attack_type.title()}."
        )

    for attack_type in explanation.closed_native_gaps:
        reductions.append(f"Closes the native-type coverage gap against {attack_type.title()}.")

    for change in explanation.increased_shared_weaknesses:
        tradeoffs.append(
            f"More members weak to {change.attack_type.title()}: "
            f"{len(change.before_members)} → {len(change.after_members)}."
        )

    for weakness in explanation.added_quad_weaknesses:
        tradeoffs.append(
            f"Adds a 4× weakness entry for "
            f"{display_name(weakness.species)} to "
            f"{weakness.attack_type.title()}."
        )

    for attack_type in explanation.opened_native_gaps:
        tradeoffs.append(f"Opens a native-type coverage gap against {attack_type.title()}.")

    st.markdown("#### What changes")

    if reductions:
        st.markdown("Reductions and removed gaps")
        st.markdown("\n".join(f"- {item}" for item in reductions))

    if tradeoffs:
        st.markdown("Tradeoffs and added weaknesses")
        st.markdown("\n".join(f"- {item}" for item in tradeoffs))

    if not reductions and not tradeoffs:
        st.caption(
            "No changes in shared-weakness counts, 4× weakness entries, "
            "or native-type coverage gaps. Other metrics may still differ."
        )

    st.caption(
        "Type-based comparison only. Native-type coverage is not selected-move "
        "coverage. Removed and added 4× entries identify member/type pairs, "
        "not necessarily a net reduction. These changes do not guarantee "
        "better battle performance."
    )
