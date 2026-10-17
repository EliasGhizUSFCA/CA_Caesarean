"""
California Birth Hospital Guide.

Streamlit dashboard that helps expectant parents compare cesarean and VBAC
rates across California hospitals.

Files:
    data.py           loads, cleans and merges the data from the GCS bucket
    basic.py          search and county overview
    advance.py        map, hospital profile and compare
"""
import streamlit as st

from advance import compare_tab, find_tab, profile_tab
from basic import TARGET_CSEC, county_tab
from data import load_data, miles_between, zip_to_latlon

# default value of every filter, used by the "Clear all selections" button
DEFAULTS = {"f_zip": "", "f_radius": 10, "f_delivers": True, "f_vbac": False,
            "f_midwife": False, "f_min_midwife": 5, "f_bf": False, "f_er": False,
            "f_stars": "Any", "f_year": "Latest available", "f_name": "",
            "f_compare": [], "f_quick": "", "f_quick_radius": 10,
            "f_page": 1, "f_per_page": 5}


def clear_selections():
    """Reset all filters. The data is not downloaded again."""
    for key, value in DEFAULTS.items():
        st.session_state[key] = value
    st.session_state.pop("f_profile", None)


if __name__ == '__main__':
    st.set_page_config(page_title="California Birth Hospital Guide", layout="wide")
    st.title("California Birth Hospital Guide")
    st.write("Compare C-section and VBAC rates, midwife care and hospital ratings "
             "across California hospitals.")

    for key, value in DEFAULTS.items():
        st.session_state.setdefault(key, value)

    with st.spinner("Loading hospital data..."):
        all_rows, files, problem = load_data()
    if problem:
        st.error(problem)
        st.stop()

    with st.sidebar:
        st.header("Search")
        st.button("Clear all selections", on_click=clear_selections,
                  use_container_width=True)
        zip_code = st.text_input("Your ZIP code", max_chars=5, key="f_zip")
        radius = st.slider("Within (miles)", 5, 100, step=5,
                           disabled=not zip_code, key="f_radius")

        st.header("Filters")
        delivers_only = st.checkbox("Delivers babies", key="f_delivers")
        want_vbac = st.checkbox("Offers VBAC (vaginal birth after a C-section)", key="f_vbac")
        want_midwife = st.checkbox("Midwife-friendly", key="f_midwife")
        min_midwife = st.slider("Midwives attend at least (%)", 1, 50,
                                disabled=not want_midwife, key="f_min_midwife")
        bf_only = st.checkbox("Birthing-friendly designation (CMS)", key="f_bf")
        er_only = st.checkbox("Has an emergency room", key="f_er")
        min_stars = st.select_slider("Minimum overall rating",
                                     ["Any", 1, 2, 3, 4, 5], key="f_stars")

        years = sorted(all_rows["year"].dropna().unique(), reverse=True)
        year_options = ["Latest available"] + [int(y) for y in years]
        if st.session_state["f_year"] not in year_options:
            st.session_state["f_year"] = "Latest available"
        year = st.selectbox("Data year", year_options, key="f_year")

    # one row per hospital
    if year == "Latest available":
        rows = all_rows
    else:
        rows = all_rows[all_rows["year"] == year]
    # latest year that has a C-section rate; if a hospital never has one, its latest row
    rows = rows.assign(has_rate=rows["csec_rate"].notna())
    hosp = (rows.sort_values(["has_rate", "year"], ascending=False, na_position="last")
            .drop_duplicates("oshpd_id").drop(columns="has_rate").copy())

    home = None
    if zip_code:
        if zip_code.isdigit() and len(zip_code) == 5:
            home = zip_to_latlon(zip_code)
            if home is None:
                st.sidebar.warning(f"Could not find ZIP code {zip_code}.")
        else:
            st.sidebar.warning("Enter a 5-digit ZIP code.")
    if home:
        hosp["miles"] = miles_between(home[0], home[1],
                                      hosp["latitude"], hosp["longitude"])

    filtered = hosp
    if delivers_only:
        filtered = filtered[filtered["delivers"]]
    if want_vbac:
        filtered = filtered[filtered["vbac_available"].fillna(False).astype(bool)]
    if want_midwife:
        filtered = filtered[filtered["midwife_pct"].fillna(0) >= min_midwife]
    if bf_only:
        filtered = filtered[filtered["birthing_friendly"].fillna(False).astype(bool)]
    if er_only:
        filtered = filtered[filtered["has_er"].fillna(False).astype(bool)]
    if min_stars != "Any":
        filtered = filtered[filtered["stars"].fillna(0) >= min_stars]
    if home:
        filtered = filtered[filtered["miles"] <= radius].sort_values("miles")
    else:
        filtered = filtered.sort_values("name")

    tab_county, tab_find, tab_profile, tab_compare, tab_about = st.tabs(
        ["Search and counties", "Find on map", "Hospital profile", "Compare",
         "About the data"])

    with tab_county:
        county_tab(hosp, filtered)

    with tab_find:
        find_tab(filtered, home)

    with tab_profile:
        profile_tab(filtered, hosp, all_rows)

    with tab_compare:
        compare_tab(filtered if not filtered.empty else hosp)

    with tab_about:
        st.subheader("What the numbers mean")
        st.markdown(f"""
- **Low-risk C-section rate**: HCAI's uncomplicated cesarean delivery rate, the share
  of low-risk births delivered by C-section. The national goal (Healthy People 2030)
  is {TARGET_CSEC}% or lower.
- **County rate**: all low-risk births in the county's hospitals combined, so larger
  hospitals count more than smaller ones.
- **VBAC rate**: of people who had a C-section before, the share who had a vaginal birth.
- **Births by midwives**: the share of births attended by certified nurse-midwives.
- **Birthing-friendly**: a CMS designation for hospitals that take part in maternity
  quality programs.
- **Overall rating**: CMS's 1 to 5 star rating of general hospital quality.
""")
        st.warning("This dashboard is for information only and is not medical advice. "
                   "Some hospitals have higher rates because they care for more "
                   "high-risk patients. Talk with your doctor or midwife.")
        st.subheader("Sources")
        st.write("HCAI, CMS Hospital General Information, CHHS licensed facility "
                 "crosswalk, and scraped hospital maternity details.")
        unique = all_rows.drop_duplicates("oshpd_id")
        st.caption(f"{len(files)} files, {len(unique)} hospitals, "
                   f"{int(unique['delivers'].sum())} deliver babies.")