"""
Simple tab: search hospitals and compare them with their county,
then C-section rate by county for all of California.
"""
import altair as alt
import pandas as pd
import streamlit as st

from data import miles_between, zip_to_latlon

# Healthy People 2030 target for low-risk (NTSV) cesarean births (%)
TARGET_CSEC = 23.6

# how many searched hospitals to show in the comparison chart
MAX_IN_CHART = 10


def pct(v) -> str:
    if pd.isna(v):
        return "No data"
    return f"{v:.1f}%"


def rating(v) -> str:
    if pd.isna(v):
        return "Not rated"
    return f"{int(v)} out of 5"


def county_rates(hosp: pd.DataFrame) -> pd.DataFrame:
    """
    C-section rate for each county.

    The county rate is weighted by births, so a large hospital counts more
    than a small one. Births are worked out from the hospital's C-section
    count and rate (births = count / rate).
    """
    df = hosp.dropna(subset=["county", "csec_rate"]).copy()
    df = df[df["csec_rate"] > 0]
    df["births"] = df["csec_count"] / (df["csec_rate"] / 100)

    rows = []
    for county, g in df.groupby("county"):
        if g["births"].notna().all() and g["births"].sum() > 0:
            rate = g["csec_count"].sum() / g["births"].sum() * 100
        else:
            rate = g["csec_rate"].median()
        rows.append({"County": county,
                     "Rate": round(rate, 1),
                     "Hospitals": len(g)})
    return pd.DataFrame(rows).sort_values("Rate", ascending=False)


def search_hospitals(hosp: pd.DataFrame, query: str, radius: int) -> pd.DataFrame | None:
    """Find hospitals by name, or by distance if the query is a ZIP code."""
    results = hosp.copy()
    if query.isdigit() and len(query) == 5:
        home = zip_to_latlon(query)
        if home is None:
            st.warning(f"Could not find ZIP code {query}.")
            return None
        results["Distance (miles)"] = miles_between(home[0], home[1],
                                                    results["latitude"], results["longitude"])
        results = results[results["Distance (miles)"] <= radius]
        return results.sort_values("Distance (miles)")
    results = results[results["name"].str.contains(query, case=False, na=False)]
    return results.sort_values("name")


def hospital_vs_county_chart(results: pd.DataFrame, counties: pd.DataFrame, state_avg):
    """Grouped bars: each searched hospital vs its county vs California."""
    county_lookup = counties.set_index("County")["Rate"]
    rows = []
    for _, r in results.dropna(subset=["csec_rate"]).head(MAX_IN_CHART).iterrows():
        rows.append({"Hospital": r["name"], "Who": "This hospital", "Rate": r["csec_rate"]})
        if r["county"] in county_lookup:
            rows.append({"Hospital": r["name"], "Who": f"County average",
                         "Rate": county_lookup[r["county"]]})
        if state_avg is not None:
            rows.append({"Hospital": r["name"], "Who": "California average", "Rate": state_avg})
    df = pd.DataFrame(rows)
    if df.empty:
        return None

    order = ["This hospital", "County average", "California average"]
    bars = alt.Chart(df).mark_bar().encode(
        x=alt.X("Rate:Q", title="Low-risk C-section rate (%)"),
        y=alt.Y("Hospital:N", title=None, sort=None),
        yOffset=alt.YOffset("Who:N", sort=order),
        color=alt.Color("Who:N",
                        scale=alt.Scale(domain=order,
                                        range=["#2a55c0", "#e0a030", "#9aa8bb"]),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=["Hospital", "Who", alt.Tooltip("Rate:Q", format=".1f")])
    goal = alt.Chart(pd.DataFrame({"goal": [TARGET_CSEC]})).mark_rule(
        strokeDash=[4, 4], color="#22784d").encode(x="goal:Q")
    height = max(160, 60 * df["Hospital"].nunique())
    return (bars + goal).properties(height=height)


def county_chart(counties: pd.DataFrame, state_avg, highlight: set):
    """Bar chart of every county; counties of searched hospitals are highlighted."""
    df = counties.copy()
    if highlight:
        df["Group"] = df["County"].apply(
            lambda c: "Your search" if c in highlight else "Other counties")
        domain = ["Your search", "Other counties"]
        colors = ["#e0a030", "#c9d1dc"]
    elif state_avg is not None:
        df["Group"] = df["Rate"].apply(
            lambda r: "Above CA average" if r > state_avg else "At or below CA average")
        domain = ["Above CA average", "At or below CA average"]
        colors = ["#c2413a", "#2a55c0"]
    else:
        df["Group"] = "County"
        domain = ["County"]
        colors = ["#2a55c0"]

    bars = alt.Chart(df).mark_bar().encode(
        x=alt.X("Rate:Q", title="Low-risk C-section rate (%)"),
        y=alt.Y("County:N", sort="-x", title=None),
        color=alt.Color("Group:N", scale=alt.Scale(domain=domain, range=colors),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=["County", alt.Tooltip("Rate:Q", format=".1f"), "Hospitals"])

    lines = [{"value": TARGET_CSEC, "label": "National goal"}]
    if state_avg is not None:
        lines.append({"value": state_avg, "label": "CA average"})
    rules = alt.Chart(pd.DataFrame(lines)).mark_rule(strokeDash=[4, 4]).encode(
        x="value:Q", color=alt.value("#333333"),
        tooltip=["label", alt.Tooltip("value:Q", format=".1f")])

    height = max(300, 18 * len(df))
    return (bars + rules).properties(height=height)


def county_tab(hosp: pd.DataFrame, filtered: pd.DataFrame):
    counties = county_rates(hosp)
    if counties.empty:
        st.info("No C-section rates available.")
        return
    state_avg = hosp["csec_state"].dropna()
    state_avg = state_avg.iloc[0] if not state_avg.empty else None

    # ---- search first ----
    st.subheader("Search a hospital")
    left, right = st.columns([3, 1])
    query = left.text_input("Hospital name or ZIP code", key="f_quick").strip()
    radius = right.slider("Distance for ZIP (miles)", 5, 100, step=5, key="f_quick_radius")

    highlight = set()
    if query:
        results = search_hospitals(filtered, query, radius)
        if results is not None and results.empty:
            st.warning("No hospitals found.")
        elif results is not None:
            highlight = set(results["county"].dropna())
            county_lookup = counties.set_index("County")["Rate"]

            table = pd.DataFrame({
                "Hospital": results["name"],
                "County": results["county"],
                "C-section rate": results["csec_rate"].map(pct),
                "County average": results["county"].map(county_lookup).map(pct),
                "CA average": results["csec_state"].map(pct),
                "Rating": results["stars"].map(rating),
            })
            if "Distance (miles)" in results:
                table.insert(2, "Distance (miles)", results["Distance (miles)"].round(1))
            st.write(f"{len(table)} hospitals found")
            st.dataframe(table, hide_index=True, use_container_width=True)

            chart = hospital_vs_county_chart(results, counties, state_avg)
            if chart is not None:
                st.markdown("**Compared with their county and California**")
                st.altair_chart(chart, use_container_width=True)
                if results["csec_rate"].notna().sum() > MAX_IN_CHART:
                    st.caption(f"Chart shows the first {MAX_IN_CHART} hospitals.")
                st.caption(f"Dashed line is the national goal of {TARGET_CSEC}%.")
    else:
        st.info("Type a hospital name (e.g. Kaiser) or a 5-digit ZIP code to compare "
                "hospitals with their county.")

    # ---- all counties ----
    st.subheader("C-section rate by county")
    st.altair_chart(county_chart(counties, state_avg, highlight), use_container_width=True)
    if highlight:
        st.caption("Counties of the hospitals you searched are highlighted.")
    st.caption(f"Dashed lines show the California average and the national goal "
               f"of {TARGET_CSEC}%.")

    c1, c2, c3 = st.columns(3)
    c1.metric("California average", pct(state_avg))
    c2.metric("Highest county", f"{counties.iloc[0]['County']} ({pct(counties.iloc[0]['Rate'])})")
    c3.metric("Lowest county", f"{counties.iloc[-1]['County']} ({pct(counties.iloc[-1]['Rate'])})")

    with st.expander("Number of hospitals in each county"):
        st.dataframe(counties[["County", "Hospitals", "Rate"]]
                     .rename(columns={"Rate": "C-section rate (%)"})
                     .sort_values("County"),
                     hide_index=True, use_container_width=True)