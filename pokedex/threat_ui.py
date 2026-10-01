import pandas as pd
import streamlit as st

from pokedex.analysis import threat_report
from pokedex.fetch import load_pokemon_cache, load_smogon_usage


@st.cache_data
def cached_usage() -> dict:
    return load_smogon_usage()


@st.cache_data
def cached_pokemon() -> dict:
    return load_pokemon_cache()


def render_meta_threats(team: dict[str, list[str]], type_chart: dict) -> None:
    usage = cached_usage()
    cache = cached_pokemon()
    st.subheader("Meta threats")
    st.caption(
        f"Top {len(usage['top'])} Pokémon in {usage['format']} ({usage['month']}), "
        "from Smogon usage stats."
    )

    threats = {r["name"]: cache[r["name"]]["types"] for r in usage["top"] if r["name"] in cache}
    report = threat_report(team, threats, type_chart)

    usage_by_name = {r["name"]: r for r in usage["top"]}
    df = pd.DataFrame(report)
    df.insert(1, "usage %", df["threat"].map(lambda n: round(usage_by_name[n]["usage"], 1)))
    df["threat"] = df["threat"].map(lambda n: usage_by_name[n]["smogon_name"])
    df = df.rename(columns={"members_weak": "# weak to it", "answers": "# can hit it 2x+"})

    dangers = df[df["danger"]]
    if dangers.empty:
        st.success("No major threats: your team has an answer to every top-30 Pokémon.")
    else:
        st.warning(f"{len(dangers)} dangerous threats: " + ", ".join(dangers["threat"]))
    st.dataframe(df.drop(columns="danger"), hide_index=True)
