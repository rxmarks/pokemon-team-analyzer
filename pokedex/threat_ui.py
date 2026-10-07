import pandas as pd
import streamlit as st

from pokedex.analysis import threat_report
from pokedex.fetch import load_pokemon_cache, load_smogon_usage
from pokedex.types import PokemonCache, Team, TypeChart, UsageData
from pokedex.usage_context import usage_context


@st.cache_data
def cached_usage() -> UsageData:
    return load_smogon_usage()


@st.cache_data
def cached_pokemon() -> PokemonCache:
    return load_pokemon_cache()


def render_meta_threats(team: Team, type_chart: TypeChart) -> None:
    """Render available usage threats without overstating data completeness."""
    usage = cached_usage()
    cache = cached_pokemon()
    entries = usage["top"]

    context = usage_context(
        usage.get("format"),
        usage.get("month"),
    )

    st.subheader("Meta threats")
    st.caption(
        f"Saved usage dataset: {context.dataset_id or 'Unavailable'} · "
        f"Usage month: {context.month or 'Unavailable'} · "
        f"{len(entries)} listed entries"
    )

    baseline = (
        str(context.weighting_baseline) if context.weighting_baseline is not None else "Unavailable"
    )
    st.caption(
        f"Weighting baseline: {baseline}. "
        "When present, this identifies the rating baseline used for "
        "usage weighting—not a strict minimum player rating."
    )

    if context.source_url is not None:
        st.markdown(f"[Smogon usage source file]({context.source_url})")
    else:
        st.caption("Source-file link unavailable: valid dataset and month metadata are required.")

    st.caption(
        "This usage list describes one battle format, not every game or server. "
        "Results use native-type matchups, not a battle simulation."
    )
    st.caption(
        "Usage % describes popularity in the saved usage dataset. "
        "Weighted datasets account for player ratings. "
        "Danger flags come from this app's type-based heuristic, "
        "not from usage percentage."
    )
    if not entries:
        st.info("No Pokémon are listed in the saved usage data.")
        return

    threats: Team = {
        row["name"]: cache[row["name"]]["types"] for row in entries if row["name"] in cache
    }

    matched_count = sum(row["name"] in cache for row in entries)
    missing_count = len(entries) - matched_count

    st.caption(
        f"Analysis coverage: {matched_count} of {len(entries)} "
        "listed entries matched the local Pokémon cache."
    )

    if not threats:
        st.info(
            "No usage-list Pokémon match the local Pokémon cache. "
            "Meta threat analysis is unavailable; other team analysis "
            "is still available."
        )
        return

    if missing_count:
        st.warning(
            f"Analyzing {matched_count} of {len(entries)} usage entries. "
            f"{missing_count} entries are missing from the local Pokémon cache."
        )

    report = threat_report(team, threats, type_chart)
    usage_by_name = {row["name"]: row for row in entries}

    df = pd.DataFrame(report)
    df.insert(
        1,
        "usage %",
        df["threat"].map(lambda name: round(usage_by_name[name]["usage"], 1)),
    )
    df["threat"] = df["threat"].map(lambda name: usage_by_name[name]["smogon_name"])
    df = df.rename(
        columns={
            "members_weak": "# weak to it",
            "answers": "# can hit it 2x+",
        }
    )

    dangers = df[df["danger"]]

    if dangers.empty:
        st.success(
            "No threats were flagged by the type-based heuristic among the analyzed Pokémon."
        )
    else:
        st.warning(
            f"{len(dangers)} threats flagged by the type-based heuristic: "
            + ", ".join(dangers["threat"].tolist())
        )

    st.dataframe(df.drop(columns="danger"), hide_index=True)
