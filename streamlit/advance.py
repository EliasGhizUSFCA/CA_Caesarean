
# AI USE: This file was written with help from Claude Opus 5.5 (Anthropic),
# through several rounds of prompts and fixes. The prompts are listed in
"""
Prompt 1: Right now the Streamlit sidebar has options to select the GCS folder and JSON files, but I dont think users should be interacting with the bucket structure. Can we remove those selectors and have the application automatically load the hospital data from GCS? Instead, add filters that are more relevant to the users, like county, hospital name, and other available hospital information. Make sure the filters are generated from the dataframe and we are not downloading the data everytime a filter changes. We can use st.cache_data for caching.
Prompt 2: I want to add an interactive map that shows all the California hospitals based on the latitude and longitude from our dataset. Also add a search functionality where users can search hospitals by name or enter a ZIP code to find nearby hospitals within a certain distance. For the ZIP search, we can use the Haversine formula to calculate the distance between the ZIP code coordinates and hospital locations. Let users select the radius in miles and update both the map and hospital list based on the search. Also make sure hospitals with missing coordinates dont cause issues when plotting.
Prompt 3: Now I want to make the dashboard more useful for expectant parents rather than just showing the cesarean rates. Can we add a filter to show only hospitals that actually deliver babies? When a hospital is selected, I want a profile that shows the cesarean rate, some basic hospital information, and a simple explanation of what the data means. Also compare the hospital rate with California average and the national goal, and if we have data for multiple years show a trend chart.
I also want to add more information like whether the hospital supports VBAC, has midwife services, CMS birthing friendly designation, hospital star rating, and if they have an emergency department. Another useful feature would be allowing users to compare upto 3 hospitals side by side. Also include the hospital address, phone number, and directions. Check what columns we already have in the dataset first, because some of these information might need another data source.
Prompt 4: The map is taking a really long time to load, especially when I change the filters. Can you check if its because we are retrieving the data from GCS again or if the map is being rendered everytime Streamlit reruns? Try optimizing it using caching so we dont have to process the same data repeatedly. Also remove the refresh data button since the data should already be loaded automatically. I want the map to respond faster without changing the existing functionality.
Prompt 5: Instead of the refresh button, lets add a "Clear All Selections" button that resets all the filters and hospital selections back to default. Use st.session_state for this and make sure it doesnt clear the cached dataset or download the files from GCS again.
Prompt 6: The map is still not showing properly and sometimes its barely visible. Can we switch the map implementation to Plotly with OpenStreetMap tiles? Use scatter_map to plot the hospital coordinates and render it with st.plotly_chart. Keep the existing search and filtering logic, I just want to change how the map is displayed. Make sure users can zoom in and see hospital information when hovering over the markers.
Prompt 7: The Plotly map is not showing at all now, but the rest of the dashboard seems to be working. Can you check if the problem is with the latitude and longitude columns, the filtered dataframe, or the Plotly configuration? Maybe try plotting a few hospitals first to see if the map works with a smaller dataset. Also check if st.plotly_chart is rendering the figure correctly. I dont want to change the entire map implementation again, just figure out whats causing the issue.
Prompt 8: Can you remove all the emojis and unnecessary decorative text from the dashboard? I want it to look more professional and simple. Also keep the coding style similar to what we had before, including the function names, comments, and overall structure.
Prompt 9: Im getting this error when deploying the Streamlit app: AttributeError: module 'plotly.express' has no attribute 'scatter_mapbox'. Here is my requirements.txt, can you check if its a Plotly version issue? If scatter_map is the newer function then update the code to use that and pin the correct Plotly version in requirements so it works both locally and on the cloud.
Prompt 10: The map is working fine in Safari but for some reason its not showing in Chrome. Im not sure if this is a browser cache issue or something with Plotly and OpenStreetMap. Can you help me debug this and check what might be causing it? Maybe we need to look at Chrome developer tools or network requests to see if the map tiles are loading correctly. Since it works in Safari I dont think we need to rewrite the map again.
Prompt 12: Can we add pagination to the hospital list? Right now its showing too many hospitals at once. Add previous and next buttons and an option to select how many hospitals to show per page. Use st.session_state to keep track of the page and reset it when filters change.

Complex tabs: hospital map, hospital profile and comparing hospitals.

"""
import altair as alt
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from basic import TARGET_CSEC, pct, rating

MAP_COLORS = {"Above CA average": "#c2413a",
              "At or below CA average": "#2a55c0",
              "No rate reported": "#9aa0a6"}


def yes_no(v) -> str:
    if pd.isna(v):
        return "Unknown"
    return "Yes" if bool(v) else "No"


def is_true(v) -> bool:
    return bool(pd.notna(v) and bool(v))


def is_false(v) -> bool:
    return bool(pd.notna(v) and not bool(v))


def highlights(r) -> str:
    """Short list of the good things to know about a hospital."""
    items = []
    if is_true(r.get("birthing_friendly")):
        items.append("Birthing-friendly (CMS)")
    if is_true(r.get("vbac_available")):
        items.append("VBAC routinely available")
    if pd.notna(r.get("midwife_pct")) and r["midwife_pct"] > 0:
        items.append(f"Midwives attend {r['midwife_pct']:.0f}% of births")
    if is_true(r.get("has_er")):
        items.append("Emergency room")
    return ", ".join(items)


def summary_sentences(r) -> list[str]:
    """Plain-language summary of one hospital."""
    lines = []
    year = f" in {int(r['year'])}" if pd.notna(r.get("year")) else ""

    if pd.notna(r["csec_rate"]):
        compare = ""
        if pd.notna(r["csec_state"]):
            diff = r["csec_rate"] - r["csec_state"]
            if diff > 0.5:
                word = "higher than"
            elif diff < -0.5:
                word = "lower than"
            else:
                word = "about the same as"
            compare = f", {word} the California average of {r['csec_state']:.1f}%"
        lines.append(f"About {r['csec_rate']:.0f} in 100 low-risk births here were "
                     f"C-sections{year}{compare}.")
        if r["csec_rate"] <= TARGET_CSEC:
            lines.append(f"This meets the national goal of {TARGET_CSEC}% or lower.")
        else:
            lines.append(f"The national goal is {TARGET_CSEC}% or lower.")
    else:
        lines.append("No C-section rate is reported for this hospital.")

    vbac = r["vbac_rate"] if pd.notna(r["vbac_rate"]) else r["vbac_pct"]
    if pd.notna(vbac):
        lines.append(f"{vbac:.0f}% of people who had a C-section before had a "
                     f"vaginal birth (VBAC) here.")
    if is_false(r.get("vbac_available")):
        lines.append("This hospital does not routinely offer VBAC.")
    if pd.notna(r["midwife_pct"]):
        lines.append(f"Certified nurse-midwives attended {r['midwife_pct']:.0f}% of births.")
    return lines


def compare_chart(r):
    """Bar chart of the hospital vs the California average vs the national goal."""
    rows = []
    if pd.notna(r["csec_rate"]):
        rows.append(("C-section (low-risk)", "This hospital", r["csec_rate"]))
        rows.append(("C-section (low-risk)", "California average", r["csec_state"]))
        rows.append(("C-section (low-risk)", "National goal", TARGET_CSEC))
    vbac = r["vbac_rate"] if pd.notna(r["vbac_rate"]) else r["vbac_pct"]
    if pd.notna(vbac):
        rows.append(("VBAC rate", "This hospital", vbac))
        rows.append(("VBAC rate", "California average", r["vbac_state"]))
    if pd.notna(r["midwife_pct"]):
        rows.append(("Births by midwives", "This hospital", r["midwife_pct"]))

    df = pd.DataFrame(rows, columns=["Measure", "Who", "Percent"]).dropna()
    if df.empty:
        return None
    order = ["This hospital", "California average", "National goal"]
    return alt.Chart(df).mark_bar().encode(
        y=alt.Y("Who:N", title=None, sort=order),
        x=alt.X("Percent:Q", title="%"),
        color=alt.Color("Who:N", legend=None,
                        scale=alt.Scale(domain=order,
                                        range=["#2a55c0", "#9aa8bb", "#22784d"])),
        row=alt.Row("Measure:N", title=None,
                    header=alt.Header(labelAngle=0, labelAlign="left")),
        tooltip=["Measure", "Who", alt.Tooltip("Percent:Q", format=".1f")],
    ).properties(height=alt.Step(22), width=420)


# AI HELP to show the hospitals on a map
def show_map(pts: pd.DataFrame, home):
    """Show the hospitals on an OpenStreetMap map."""
    total = len(pts)
    pts = pts.dropna(subset=["latitude", "longitude"]).copy()
    if pts.empty:
        st.info("None of these hospitals have map coordinates.")
        return

    rate = pts["csec_rate"]
    state = pts["csec_state"]
    category = np.where(rate.isna(), "No rate reported",
                        np.where(rate > state, "Above CA average", "At or below CA average"))
    map_data = pd.DataFrame({
        "Hospital": pts["name"].fillna("").astype(str),
        "County": pts["county"].fillna("").astype(str),
        "lat": pts["latitude"].astype(float),
        "lon": pts["longitude"].astype(float),
        "C-section rate": category,
        "Rate": rate.map(pct),
        "CA average": state.map(pct),
        "Rating": pts["stars"].map(rating),
    })

    if home:
        center = {"lat": home[0], "lon": home[1]}
        zoom = 9
    else:
        center = {"lat": map_data["lat"].mean(), "lon": map_data["lon"].mean()}
        zoom = 10 if len(map_data) < 5 else 5

    settings = dict(lat="lat", lon="lon",
                    color="C-section rate",
                    color_discrete_map=MAP_COLORS,
                    category_orders={"C-section rate": list(MAP_COLORS)},
                    hover_name="Hospital",
                    hover_data={"County": True, "Rate": True,
                                "CA average": True, "Rating": True,
                                "lat": False, "lon": False,
                                "C-section rate": False},
                    zoom=zoom, center=center, height=560)

    # newer plotly uses scatter_map, older plotly uses scatter_mapbox
    if hasattr(px, "scatter_map"):
        fig = px.scatter_map(map_data, map_style="open-street-map", **settings)
        home_marker = go.Scattermap
    else:
        fig = px.scatter_mapbox(map_data, mapbox_style="open-street-map", **settings)
        home_marker = go.Scattermapbox

    fig.update_traces(marker={"size": 13, "opacity": 0.9})
    if home:
        fig.add_trace(home_marker(lat=[home[0]], lon=[home[1]], mode="markers",
                                  marker={"size": 16, "color": "black"},
                                  name="Your ZIP", hoverinfo="name"))
    fig.update_layout(margin={"l": 0, "r": 0, "t": 0, "b": 0},
                      legend={"orientation": "h", "y": 1.02, "x": 0, "title": None})
    st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True})

    if total > len(map_data):
        st.caption(f"{total - len(map_data)} hospitals are not on the map "
                   f"because they have no coordinates.")


def hospital_card(r):
    with st.container(border=True):
        left, right = st.columns([3, 1])
        distance = ""
        if "miles" in r and pd.notna(r.get("miles")):
            distance = f", {r['miles']:.1f} miles away"
        left.markdown(f"**{r['name']}**  \n{r['county'] or ''}{distance}")
        right.markdown(f"C-section: **{pct(r['csec_rate'])}**  \nRating: {rating(r['stars'])}")
        if highlights(r):
            st.caption(highlights(r))


def find_tab(filtered: pd.DataFrame, home):
    name_search = st.text_input("Search by hospital name", key="f_name")
    if name_search:
        results = filtered[filtered["name"].str.contains(name_search, case=False, na=False)]
    else:
        results = filtered

    k1, k2, k3 = st.columns(3)
    k1.metric("Hospitals found", len(results))
    k2.metric("Median low-risk C-section rate", pct(results["csec_rate"].median()))
    k3.metric("Offer VBAC", int(results["vbac_available"].fillna(False).astype(bool).sum()))

    if results.empty:
        st.warning("No hospitals match. Try a larger distance or fewer filters.")
        return
    show_map(results, home)
    st.subheader("Nearest hospitals" if home else "Hospitals")
    hospital_list(results)


def go_to_page(page: int):
    st.session_state["f_page"] = page


def hospital_list(results: pd.DataFrame):
    """Show the hospital cards a few at a time with previous / next buttons."""
    per_page = st.selectbox("Hospitals per page", [5, 10, 25, 50], key="f_per_page")
    pages = max(1, -(-len(results) // per_page))      # round up

    # go back to page 1 when the search or filters change the results
    signature = (len(results), tuple(results["oshpd_id"].head(5)), per_page)
    if st.session_state.get("f_list_signature") != signature:
        st.session_state["f_list_signature"] = signature
        st.session_state["f_page"] = 1
    page = min(st.session_state.get("f_page", 1), pages)

    start = (page - 1) * per_page
    for _, r in results.iloc[start:start + per_page].iterrows():
        hospital_card(r)

    prev_col, info_col, next_col = st.columns([1, 2, 1])
    prev_col.button("Previous", on_click=go_to_page, args=(page - 1,),
                    disabled=page <= 1, use_container_width=True)
    info_col.markdown(f"<div style='text-align:center'>Page {page} of {pages} "
                      f"({start + 1} to {min(start + per_page, len(results))} "
                      f"of {len(results)} hospitals)</div>",
                      unsafe_allow_html=True)
    next_col.button("Next", on_click=go_to_page, args=(page + 1,),
                    disabled=page >= pages, use_container_width=True)


def profile(r, history: pd.DataFrame):
    st.header(r["name"])
    if highlights(r):
        st.write(highlights(r))

    c1, c2, c3 = st.columns(3)
    delta = None
    if pd.notna(r["csec_rate"]) and pd.notna(r["csec_state"]):
        delta = f"{r['csec_rate'] - r['csec_state']:+.1f} vs CA"
    c1.metric("Low-risk C-section rate", pct(r["csec_rate"]),
              delta=delta, delta_color="inverse")
    c2.metric("Overall rating (CMS)", rating(r["stars"]))
    c3.metric("VBAC routinely offered", yes_no(r["vbac_available"]))

    st.subheader("Summary")
    for line in summary_sentences(r):
        st.markdown(f"- {line}")

    st.subheader("Compared with California")
    chart = compare_chart(r)
    if chart is not None:
        st.altair_chart(chart, use_container_width=False)
        st.caption("For low-risk births, a lower C-section rate is generally better. "
                   "A higher VBAC rate means more people who wanted a vaginal birth "
                   "after a C-section were able to have one.")
    else:
        st.info("No rates reported for this hospital.")

    trend = history.dropna(subset=["year", "csec_rate"]).sort_values("year")
    if len(trend) > 1:
        st.subheader("Trend over the years")
        hospital_line = (trend[["year", "csec_rate"]]
                         .rename(columns={"csec_rate": "Percent"})
                         .assign(Who="This hospital"))
        state_line = (trend[["year", "csec_state"]]
                      .rename(columns={"csec_state": "Percent"})
                      .assign(Who="California average"))
        t = pd.concat([hospital_line, state_line]).dropna()
        line = alt.Chart(t).mark_line(point=True).encode(
            x=alt.X("year:O", title="Year"),
            y=alt.Y("Percent:Q", title="Low-risk C-section rate (%)",
                    scale=alt.Scale(zero=False)),
            color=alt.Color("Who:N", scale=alt.Scale(range=["#2a55c0", "#9aa8bb"]),
                            legend=alt.Legend(orient="bottom", title=None)),
            tooltip=["year", "Who", alt.Tooltip("Percent:Q", format=".1f")])
        goal = alt.Chart(pd.DataFrame({"goal": [TARGET_CSEC]})).mark_rule(
            strokeDash=[4, 4], color="#22784d").encode(y="goal:Q")
        st.altair_chart(line + goal, use_container_width=True)
        st.caption(f"The dashed line is the national goal of {TARGET_CSEC}%.")

    st.subheader("Contact")
    st.write(f"Address: {r['address'] or 'Not available'}")
    if pd.notna(r["phone"]):
        st.write(f"Phone: {r['phone']}")
    st.link_button("Get directions", r["directions"])


def profile_tab(filtered: pd.DataFrame, hosp: pd.DataFrame, all_rows: pd.DataFrame):
    choices = filtered if not filtered.empty else hosp
    options = choices["name"].dropna().unique().tolist()
    if st.session_state.get("f_profile") not in options:
        st.session_state.pop("f_profile", None)
    pick = st.selectbox("Choose a hospital", options, key="f_profile")
    if pick:
        r = hosp[hosp["name"] == pick].iloc[0]
        history = all_rows[all_rows["oshpd_id"] == r["oshpd_id"]]
        profile(r, history)


def compare_tab(hosp: pd.DataFrame):
    st.subheader("Compare up to 3 hospitals")
    names = hosp["name"].dropna().sort_values().unique().tolist()
    # remove hospitals that the current filters no longer include
    st.session_state["f_compare"] = [p for p in st.session_state.get("f_compare", [])
                                     if p in names]
    picks = st.multiselect("Choose hospitals", names, max_selections=3, key="f_compare")
    if not picks:
        st.info("Pick two or three hospitals to compare them.")
        return

    sel = hosp.drop_duplicates("name").set_index("name").loc[picks]
    table = pd.DataFrame({
        "Low-risk C-section rate": sel["csec_rate"].map(pct),
        "California average": sel["csec_state"].map(pct),
        "VBAC rate": sel["vbac_rate"].fillna(sel["vbac_pct"]).map(pct),
        "VBAC routinely offered": sel["vbac_available"].map(yes_no),
        "Births by midwives": sel["midwife_pct"].map(pct),
        "Birthing-friendly (CMS)": sel["birthing_friendly"].map(yes_no),
        "Overall rating": sel["stars"].map(rating),
        "Emergency room": sel["has_er"].map(yes_no),
        "Phone": sel["phone"].fillna("Not available"),
        "Address": sel["address"].fillna("Not available"),
    })
    if "miles" in sel:
        table["Distance"] = sel["miles"].map(lambda v: f"{v:.1f} miles" if pd.notna(v) else "")
    st.dataframe(table.T, use_container_width=True)

    cols = st.columns(len(picks))
    for col, (name, r) in zip(cols, sel.iterrows()):
        col.link_button(f"Directions to {name}", r["directions"], use_container_width=True)