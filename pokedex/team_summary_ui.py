"""Streamlit presentation for structured team-summary facts."""

import streamlit as st

from pokedex.display import display_name, type_badges
from pokedex.team_summary import TeamSummary

MAX_SUMMARY_ITEMS = 3


def render_team_summary(
    summary: TeamSummary,
    *,
    selected_count: int,
    analyzed_count: int,
) -> None:
    """Show type-based findings before optional detailed tables."""
    st.markdown("### At a glance")
    st.caption(
        "A starting point for exploring your team—"
        "not a battle simulation or an overall team rating. "
        "These findings use Pokémon types; selected moves are checked separately."
    )

    if analyzed_count < selected_count:
        st.warning(
            f"Partial analysis: loaded {analyzed_count} of "
            f"{selected_count} selected Pokémon. "
            "These findings exclude members whose data could not be loaded."
        )

    shared, big, coverage = st.columns(3)

    with shared:
        with st.container(border=True):
            st.markdown("#### Shared weaknesses")
            st.caption("Attack types that hit more than one member super-effectively.")
            if summary.shared_weaknesses:
                shown = summary.shared_weaknesses[:MAX_SUMMARY_ITEMS]
                st.markdown(
                    type_badges([weakness.attack_type for weakness in shown]),
                    unsafe_allow_html=True,
                )
                for weakness in shown:
                    members = ", ".join(display_name(name) for name in weakness.members)
                    st.markdown(
                        f"- {weakness.attack_type.title()} "
                        f"({len(weakness.members)} members: {members})"
                    )
                remaining = len(summary.shared_weaknesses) - len(shown)
                if remaining:
                    st.caption(f"Plus {remaining} more attack types. See Defensive coverage below.")
            else:
                st.markdown("No shared type weaknesses among the analyzed members.")

    with big:
        with st.container(border=True):
            st.markdown("#### Big weaknesses · 4×")
            st.caption("Type matchups that deal four times normal damage, before other effects.")
            if summary.quad_weaknesses:
                shown_quad = summary.quad_weaknesses[:MAX_SUMMARY_ITEMS]
                st.markdown(
                    type_badges(list(dict.fromkeys(w.attack_type for w in shown_quad))),
                    unsafe_allow_html=True,
                )
                for quad_weakness in shown_quad:
                    st.markdown(
                        f"- {display_name(quad_weakness.species)} "
                        f"to {quad_weakness.attack_type.title()}"
                    )
                remaining = len(summary.quad_weaknesses) - len(shown_quad)
                if remaining:
                    st.caption(f"Plus {remaining} more matchups. See Defensive coverage below.")
            else:
                st.markdown("No 4× type weaknesses among the analyzed members.")

    with coverage:
        with st.container(border=True):
            st.markdown("#### Types to cover")
            st.caption("Types your Pokémon’s own attack types cannot hit super-effectively.")
            if summary.native_coverage_gaps:
                st.markdown(type_badges(list(summary.native_coverage_gaps)), unsafe_allow_html=True)
                st.markdown(
                    "Selected moves may fill these gaps. Check Coverage from selected moves "
                    "before considering a replacement."
                )
            else:
                st.markdown(
                    "Your Pokémon’s types cover every single type super-effectively. "
                    "This does not verify which moves they actually have."
                )

    st.caption(
        "You do not need to fix every finding. Explore optional changes in Swap suggestions "
        "and preview their tradeoffs before applying them."
    )
