"""Streamlit presentation for structured team-summary facts."""

import streamlit as st

from pokedex.display import display_name
from pokedex.team_summary import TeamSummary

MAX_SUMMARY_ITEMS = 3


def render_team_summary(
    summary: TeamSummary,
    *,
    selected_count: int,
    analyzed_count: int,
) -> None:
    """Show a compact, explicitly type-based review checklist."""
    st.markdown("### What to review")
    st.caption(
        "Type-based checks only—not a battle simulation or an overall team rating. "
        "Selected moves are analyzed separately in the Team builder tab."
    )

    if analyzed_count < selected_count:
        st.warning(
            f"Partial analysis: loaded {analyzed_count} of "
            f"{selected_count} selected Pokémon. "
            "These findings exclude members whose data could not be loaded."
        )

    if summary.shared_weaknesses:
        details = "; ".join(
            (
                f"{weakness.attack_type.title()} "
                f"({len(weakness.members)} members: "
                f"{', '.join(display_name(name) for name in weakness.members)})"
            )
            for weakness in summary.shared_weaknesses[:MAX_SUMMARY_ITEMS]
        )
        remaining = len(summary.shared_weaknesses) - MAX_SUMMARY_ITEMS
        extra = ""
        if remaining > 0:
            noun = "attack type" if remaining == 1 else "attack types"
            extra = f"; plus {remaining} other {noun}"
        st.markdown(
            f"- Shared weaknesses: {details}{extra}. "
            "Review Defensive coverage in Team builder before considering replacements."
        )
    else:
        st.markdown(
            "- Shared weaknesses: no attack type hits two or more "
            "analyzed members super-effectively."
        )

    if summary.quad_weaknesses:
        details = "; ".join(
            (f"{display_name(weakness.species)} to {weakness.attack_type.title()}")
            for weakness in summary.quad_weaknesses[:MAX_SUMMARY_ITEMS]
        )
        remaining = len(summary.quad_weaknesses) - MAX_SUMMARY_ITEMS
        extra = ""
        if remaining > 0:
            noun = "member/type pair" if remaining == 1 else "member/type pairs"
            extra = f"; plus {remaining} other {noun}"

        st.markdown(
            f"- 4× weaknesses: {details}{extra}. See Defense for the complete multiplier table."
        )
    else:
        st.markdown("- 4× weaknesses: none among the analyzed members.")

    if summary.native_coverage_gaps:
        gaps = ", ".join(attack_type.title() for attack_type in summary.native_coverage_gaps)
        st.markdown(
            f"- Native-type coverage gaps: {gaps}. "
            "Check selected moves in Team builder before deciding "
            "a replacement is needed."
        )
    else:
        st.markdown(
            "- Native-type coverage gaps: none. "
            "This does not verify which moves your Pokémon actually have."
        )

    st.caption(
        "Swap suggestions are optional alternatives within your replacement pool. "
        "Preview their tradeoffs; a lower type-based score does not guarantee "
        "better battle performance."
    )
