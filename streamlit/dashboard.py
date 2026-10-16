"""
California Birth Hospital Guide.

Streamlit dashboard that reads hospital data from the GCS bucket (hospital/)
and helps expectant parents compare cesarean and VBAC rates across hospitals.

Folders read from the bucket:
    hcai/               cesarean and VBAC rates by hospital and year
    scraped-hospitals/  scraped maternity details
    crosswalk/          HCAI_ID to CCN crosswalk
    cms/                CMS hospital general information
"""
import json
import re
import urllib.parse

import altair as alt
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from google.cloud import storage
from google.oauth2 import service_account

from user_definition import (bucket_name, project_id,
                             service_account_file_path)

FOLDER = "hospital/"
CROSSWALK_FOLDER = "crosswalk"
SCRAPED_FOLDER = "scraped-hospitals"
HCAI_FOLDER = "hcai"
CMS_FOLDER = "cms"

# Healthy People 2030 target for low-risk (NTSV) cesarean births (%)
TARGET_CSEC = 23.6

MAP_COLORS = {"Above CA average": "#c2413a",
              "At or below CA average": "#2a55c0",
              "No rate reported": "#9aa0a6"}

# default value of every filter, used by the "Clear all selections" button
DEFAULTS = {"f_zip": "", "f_radius": 10, "f_delivers": True, "f_vbac": False,
            "f_midwife": False, "f_min_midwife": 5, "f_bf": False, "f_er": False,
            "f_stars": "Any", "f_year": "Latest available", "f_name": "",
            "f_compare": []}


@st.cache_data(ttl=3600)
def retrieve_data_from_gcs(service_account_key: str,
                           project_id: str,
                           bucket_name: str,
                           folder: str) -> tuple[pd.DataFrame, list[str]]:
    """
    Read every .json file under 'folder' in 'bucket_name' and combine them
    into one DataFrame.

    """
    # connect to GCS and get the bucket
    credentials = service_account.Credentials.from_service_account_file(
        service_account_key)
    client = storage.Client(project=project_id,
                            credentials=credentials)
    bucket = client.bucket(bucket_name)

    frames = []
    files_read = []
    for blob in bucket.list_blobs(prefix=folder):
        if not blob.name.endswith(".json"):
            continue
        raw = blob.download_as_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        df = pd.json_normalize(json.loads(text)).astype(str)
        relative = blob.name[len(folder):]
        df["source_folder"] = "/".join(relative.split("/")[:-1])
        frames.append(df)
        files_read.append(blob.name)

    if not frames:
        return pd.DataFrame(), files_read
    return pd.concat(frames, ignore_index=True), files_read


def part(data: pd.DataFrame, folder: str) -> pd.DataFrame:
    """Return the rows that came from one subfolder, without empty columns."""
    if data.empty:
        return data
    rows = data[data["source_folder"].str.split("/").str[0] == folder]
    rows = rows.replace({"nan": None, "None": None, "": None, "NaN": None})
    rows = rows.dropna(axis=1, how="all")
    return rows.drop(columns=["source_folder"], errors="ignore")


# AI HELP to clean the data from the bucket
def clean_id(col: pd.Series, width: int | None = None) -> pd.Series:
    """Strip spaces and '.0', remove empty values, and zero-pad if needed."""
    s = col.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    s = s.where(~s.str.upper().isin(["NONE", "NAN", "", "EXCLUDED"]))
    if width:
        return s.str.zfill(width)
    return s


def snake(text) -> str:
    """'Uncomplicated Cesarean Delivery' -> 'uncomplicated_cesarean_delivery'"""
    return re.sub(r"[^0-9a-z]+", "_", str(text).lower()).strip("_")


def num(df: pd.DataFrame, col: str) -> pd.Series:
    if col in df:
        return pd.to_numeric(df[col], errors="coerce")
    return pd.Series(np.nan, index=df.index)


def flag(df: pd.DataFrame, col: str) -> pd.Series:
    """Turn 'True'/'Y'/'Yes' into True and 'False'/'N'/'No' into False."""
    if col not in df:
        return pd.Series(pd.NA, index=df.index, dtype="boolean")
    values = {"true": True, "y": True, "yes": True, "1": True,
              "false": False, "n": False, "no": False, "0": False}
    return (df[col].astype(str).str.strip().str.lower()
            .map(values).astype("boolean"))


def text(df: pd.DataFrame, col: str) -> pd.Series:
    if col in df:
        return df[col]
    return pd.Series(None, index=df.index, dtype="object")


def find_col(df: pd.DataFrame, *words) -> str | None:
    """First column whose name contains all 'words' (statewide columns skipped)."""
    for c in df.columns:
        if all(w in c for w in words) and not c.startswith("state_"):
            return c
    return None


# AI HELP to merge all the data from the four sources into one dataframe
def merge_all(xwalk, scraped, hcai, cms) -> pd.DataFrame:
    """Merge the four sources into one row per hospital per year."""
    # HCAI: one row per procedure -> one row per hospital and year
    h = hcai.copy()
    h["oshpd_id"] = clean_id(h["OSHPD_ID"])
    h["procedure"] = h["Procedure"].map(snake)
    for col in ["Year", "Rate", "Count", "Latitude", "Longitude"]:
        h[col] = pd.to_numeric(h.get(col), errors="coerce")
    is_state = (h["Hospital"].astype(str).str.upper() == "STATEWIDE") | h["oshpd_id"].isna()

    state = h[is_state].pivot_table(index="Year", columns="procedure",
                                    values="Rate", aggfunc="first")
    state.columns = [f"state_{p}_rate" for p in state.columns]

    hosp = h[~is_state].drop_duplicates(["oshpd_id", "Year", "procedure"])
    wide = hosp.pivot_table(index=["oshpd_id", "Year"], columns="procedure",
                            values=["Rate", "Count"], aggfunc="first")
    wide.columns = [f"{proc}_{val.lower()}" for val, proc in wide.columns]
    wide = wide.reset_index().rename(columns={"Year": "year"})
    info = hosp.groupby("oshpd_id").agg(hcai_hospital=("Hospital", "first"),
                                        county=("County", "first"),
                                        latitude=("Latitude", "first"),
                                        longitude=("Longitude", "first")).reset_index()

    # scraped hospitals
    s = scraped.copy()
    s["oshpd_id"] = clean_id(s["oshpd_id"])
    s = s[s["oshpd_id"].notna()].drop_duplicates("oshpd_id")
    s = s.rename(columns={c: f"scraped_{c}" for c in s.columns if c != "oshpd_id"})

    # crosswalk
    x = xwalk.copy()
    x["oshpd_id"] = clean_id(x["HCAI_ID"])
    x = x[x["oshpd_id"].notna()].drop_duplicates("oshpd_id")
    x["ccn"] = clean_id(x["CCN"], 6)
    x = x[["oshpd_id", "ccn", "FACNAME"]].rename(columns={"FACNAME": "crosswalk_facname"})

    # CMS
    if not cms.empty and "Facility ID" in cms:
        c = cms.copy()
        c["ccn"] = clean_id(c["Facility ID"], 6)
        c = c[c["ccn"].notna()].drop_duplicates("ccn").drop(columns=["Facility ID"])
        c = c.rename(columns={col: f"cms_{snake(col)}" for col in c.columns if col != "ccn"})
    else:
        c = pd.DataFrame(columns=["ccn"])

    ids = pd.concat([wide["oshpd_id"], s["oshpd_id"]]).dropna().unique()
    merged = (pd.DataFrame({"oshpd_id": ids})
              .merge(info, on="oshpd_id", how="left")
              .merge(s, on="oshpd_id", how="left")
              .merge(x, on="oshpd_id", how="left")
              .merge(c, on="ccn", how="left")
              .merge(wide, on="oshpd_id", how="left")
              .merge(state, left_on="year", right_index=True, how="left"))
    merged["year"] = merged["year"].astype("Int64")
    return merged


# AI HELP to add the cleaned columns used by the dashboard
def enrich(m: pd.DataFrame) -> pd.DataFrame:
    """Add the cleaned and typed columns that the dashboard uses."""
    m = m.copy()
    csec = find_col(m, "cesarean", "_rate")
    vbac = find_col(m, "vbac", "_rate")
    csec_n = find_col(m, "cesarean", "_count")

    m["name"] = (text(m, "scraped_hospital_name")
                 .fillna(text(m, "hcai_hospital"))
                 .fillna(text(m, "crosswalk_facname"))
                 .fillna(text(m, "cms_facility_name")))
    m["county"] = text(m, "county").fillna(text(m, "cms_county_parish")).str.title()

    m["csec_rate"] = num(m, csec) if csec else np.nan
    m["csec_state"] = num(m, f"state_{csec}") if csec else np.nan
    m["csec_count"] = num(m, csec_n) if csec_n else np.nan
    m["vbac_rate"] = num(m, vbac) if vbac else np.nan
    m["vbac_state"] = num(m, f"state_{vbac}") if vbac else np.nan

    m["ntsv_pct"] = num(m, "scraped_ntsv_cesarean_pct")
    m["vbac_pct"] = num(m, "scraped_vbac_pct")
    m["midwife_pct"] = num(m, "scraped_cnm_delivery_pct")
    m["vbac_available"] = flag(m, "scraped_vbac_routinely_available")
    m["maternity"] = flag(m, "scraped_has_maternity_section")

    m["birthing_friendly"] = flag(m, "cms_meets_criteria_for_birthing_friendly_designation")
    m["stars"] = num(m, "cms_hospital_overall_rating")
    m["has_er"] = flag(m, "cms_emergency_services")
    m["phone"] = text(m, "cms_telephone_number")

    addresses = []
    for street, city, zip_code in zip(text(m, "cms_address"), text(m, "cms_city_town"),
                                      text(m, "cms_zip_code")):
        if pd.isna(street):
            addresses.append(None)
        else:
            addresses.append(f"{street}, {city}, CA {zip_code}")
    m["address"] = addresses
    m["directions"] = ["https://www.google.com/maps/dir/?api=1&destination="
                       + urllib.parse.quote_plus(a if a else f"{n}, California")
                       for a, n in zip(m["address"], m["name"])]

    # a hospital delivers babies if the scraper says so or it has birth data
    has_births = (m["csec_count"].fillna(0) > 0) | m["ntsv_pct"].notna() | m["csec_rate"].notna()
    m["delivers"] = m["maternity"].fillna(False).astype(bool) | has_births
    m["latitude"] = pd.to_numeric(m["latitude"], errors="coerce")
    m["longitude"] = pd.to_numeric(m["longitude"], errors="coerce")
    return m


@st.cache_data(ttl=3600, show_spinner=False)
def load_data() -> tuple[pd.DataFrame, list[str], str | None]:
    """Download and merge everything once an hour."""
    data, files = retrieve_data_from_gcs(service_account_file_path,
                                         project_id,
                                         bucket_name,
                                         FOLDER)
    if data.empty:
        return pd.DataFrame(), files, f"No data found under {FOLDER} in the bucket."

    xwalk = part(data, CROSSWALK_FOLDER)
    scraped = part(data, SCRAPED_FOLDER)
    hcai = part(data, HCAI_FOLDER)
    cms = part(data, CMS_FOLDER)

    missing = [name for name, df in [(CROSSWALK_FOLDER, xwalk),
                                     (SCRAPED_FOLDER, scraped),
                                     (HCAI_FOLDER, hcai)] if df.empty]
    if missing:
        return pd.DataFrame(), files, f"No data in {', '.join(missing)}."
    return enrich(merge_all(xwalk, scraped, hcai, cms)), files, None


# AI HELP to get the location of the zip code
@st.cache_data(ttl=86400)
def zip_to_latlon(zipcode: str) -> tuple[float, float] | None:
    """Look up the latitude and longitude of a US ZIP code."""
    try:
        r = requests.get(f"https://api.zippopotam.us/us/{zipcode}", timeout=10)
        if r.status_code != 200:
            return None
        place = r.json()["places"][0]
        return float(place["latitude"]), float(place["longitude"])
    except Exception:
        return None


def miles_between(lat1, lon1, lat2, lon2):
    """Distance in miles between two points (haversine formula)."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = (np.sin((lat2 - lat1) / 2) ** 2
         + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2)
    return 3958.8 * 2 * np.arcsin(np.sqrt(a))


def pct(v) -> str:
    if pd.isna(v):
        return "No data"
    return f"{v:.1f}%"


def yes_no(v) -> str:
    if pd.isna(v):
        return "Unknown"
    return "Yes" if bool(v) else "No"


def rating(v) -> str:
    if pd.isna(v):
        return "Not rated"
    return f"{int(v)} out of 5"


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


#AI HELP to show the hospitals on a map and display the hospital profile
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

    # scatter_mapbox with open-street-map works in every Streamlit version
    # and does not need a Mapbox token
    fig = px.scatter_mapbox(map_data, lat="lat", lon="lon",
                            color="C-section rate",
                            color_discrete_map=MAP_COLORS,
                            category_orders={"C-section rate": list(MAP_COLORS)},
                            hover_name="Hospital",
                            hover_data={"County": True, "Rate": True,
                                        "CA average": True, "Rating": True,
                                        "lat": False, "lon": False,
                                        "C-section rate": False},
                            mapbox_style="open-street-map",
                            zoom=zoom, center=center, height=560)
    fig.update_traces(marker={"size": 13, "opacity": 0.9})
    if home:
        fig.add_trace(go.Scattermapbox(lat=[home[0]], lon=[home[1]], mode="markers",
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


def compare_section(hosp: pd.DataFrame):
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
    hosp = (rows.sort_values("year", ascending=False, na_position="last")
            .drop_duplicates("oshpd_id").copy())

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

    tab_find, tab_profile, tab_compare, tab_about = st.tabs(
        ["Find a hospital", "Hospital profile", "Compare", "About the data"])

    with tab_find:
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
        else:
            show_map(results, home)
            st.subheader("Nearest hospitals" if home else "Hospitals")
            for _, r in results.head(5).iterrows():
                hospital_card(r)
            if len(results) > 5:
                st.caption(f"Showing 5 of {len(results)} hospitals.")

    with tab_profile:
        choices = filtered if not filtered.empty else hosp
        options = choices["name"].dropna().unique().tolist()
        if st.session_state.get("f_profile") not in options:
            st.session_state.pop("f_profile", None)
        pick = st.selectbox("Choose a hospital", options, key="f_profile")
        if pick:
            r = hosp[hosp["name"] == pick].iloc[0]
            history = all_rows[all_rows["oshpd_id"] == r["oshpd_id"]]
            profile(r, history)

    with tab_compare:
        compare_section(filtered if not filtered.empty else hosp)

    with tab_about:
        st.subheader("What the numbers mean")
        st.markdown(f"""
- **Low-risk C-section rate**: HCAI's uncomplicated cesarean delivery rate, the share
  of low-risk births delivered by C-section. The national goal (Healthy People 2030)
  is {TARGET_CSEC}% or lower.
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