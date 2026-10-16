"""California Birth Hospital Guide — Streamlit dashboard for expectant parents.

Data (all from the GCS bucket, folder hospital/):
    hcai/               HCAI cesarean & VBAC rates by hospital and year (+ statewide)
    scraped-hospitals/  scraped maternity details (NTSV %, VBAC %, midwife %, maternity unit)
    crosswalk/          ID crosswalk  HCAI_ID <-> CCN
    cms/                CMS Hospital General Information (address, phone, stars, ER,
                        birthing-friendly designation)
"""
import io
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

MAP_COLORS = {"Above CA average": "#c2413a",
              "At or below CA average": "#2a55c0",
              "No rate reported": "#9aa0a6"}

TARGET_CSEC = 23.6   # Healthy People 2030 target for low-risk (NTSV) cesarean births, %

TOUR_QUESTIONS = {
    "Birth plan & interventions": [
        "What is your C-section rate for first-time, low-risk births?",
        "How do you decide when to induce labor or recommend a C-section?",
        "Can I move around, eat or drink, and choose my position during labor?",
        "What pain relief options do you offer (epidural, nitrous oxide, tub, none)?",
    ],
    "VBAC (if you had a C-section before)": [
        "Do you support VBAC / TOLAC, and is an anesthesiologist and OB in-house 24/7?",
        "How many VBACs do you do each year, and what is your success rate?",
    ],
    "Care team": [
        "Are certified nurse-midwives on staff? Can they attend my birth?",
        "Who will be with me during labor — my own provider or whoever is on call?",
        "Do you allow a doula, and how many support people can be in the room?",
    ],
    "Baby care": [
        "What level is your NICU? If my baby needs more, where would they be transferred?",
        "Is skin-to-skin contact right after birth routine, including after a C-section?",
        "Does my baby stay in my room (rooming-in)? Is lactation support available?",
    ],
    "Practical": [
        "Is the hospital in my insurance network? What will I likely pay?",
        "Where do I park and which entrance do I use when labor starts?",
        "Are interpreters available in my language?",
        "Can I pre-register and take a tour of the labor & delivery unit?",
    ],
}


# =====================================================================
# Loading
# =====================================================================
@st.cache_data(ttl=3600)
def retrieve_data_from_gcs(service_account_key: str, project_id: str,
                           bucket_name: str, folder: str) -> tuple[pd.DataFrame, list[str]]:
    """Read every .json file under `folder` (all subfolders) into one DataFrame."""
    credentials = service_account.Credentials.from_service_account_file(service_account_key)
    bucket = storage.Client(project=project_id, credentials=credentials).bucket(bucket_name)

    frames, files_read = [], []
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
        df["source_folder"] = "/".join(relative.split("/")[:-1]) or "(root)"
        frames.append(df)
        files_read.append(blob.name)

    data = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return data, files_read


def part(data: pd.DataFrame, folder: str) -> pd.DataFrame:
    """Rows from one top-level subfolder, with all-empty columns removed."""
    if data.empty:
        return data
    rows = data[data["source_folder"].str.split("/").str[0] == folder]
    rows = rows.replace({"nan": None, "None": None, "": None, "NaN": None}).dropna(axis=1, how="all")
    return rows.drop(columns=["source_folder"], errors="ignore")


# =====================================================================
# Cleaning helpers
# =====================================================================
def clean_id(col: pd.Series, width: int | None = None) -> pd.Series:
    s = col.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    s = s.where(~s.str.upper().isin(["NONE", "NAN", "", "EXCLUDED"]))
    return s.str.zfill(width) if width else s


def snake(text) -> str:
    return re.sub(r"[^0-9a-z]+", "_", str(text).lower()).strip("_")


def num(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(df[col], errors="coerce") if col in df else pd.Series(np.nan, index=df.index)


def flag(df: pd.DataFrame, col: str) -> pd.Series:
    """'True'/'Y'/'Yes' -> True, 'False'/'N'/'No' -> False, anything else -> missing."""
    if col not in df:
        return pd.Series(pd.NA, index=df.index, dtype="boolean")
    m = {"true": True, "y": True, "yes": True, "1": True,
         "false": False, "n": False, "no": False, "0": False}
    return df[col].astype(str).str.strip().str.lower().map(m).astype("boolean")


def text(df: pd.DataFrame, col: str) -> pd.Series:
    return df[col] if col in df else pd.Series(None, index=df.index, dtype="object")


def find_col(df: pd.DataFrame, *words, exclude="state_") -> str | None:
    for c in df.columns:
        if all(w in c for w in words) and not c.startswith(exclude):
            return c
    return None


# =====================================================================
# Merge all four sources -> one row per hospital per year
# =====================================================================
def merge_all(xwalk, scraped, hcai, cms) -> pd.DataFrame:
    # ---- HCAI: long -> one row per hospital-year ----
    h = hcai.copy()
    h["oshpd_id"] = clean_id(h["OSHPD_ID"]) if "OSHPD_ID" in h else None
    h["procedure"] = h["Procedure"].map(snake)
    for col in ("Year", "Rate", "Count", "Latitude", "Longitude"):
        h[col] = pd.to_numeric(h.get(col), errors="coerce")
    is_state = h["Hospital"].astype(str).str.upper().eq("STATEWIDE") | h["oshpd_id"].isna()

    state = h[is_state].pivot_table(index="Year", columns="procedure", values="Rate", aggfunc="first")
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

    # ---- scraped ----
    s = scraped.copy()
    s["oshpd_id"] = clean_id(s["oshpd_id"])
    s = s[s["oshpd_id"].notna()].drop_duplicates("oshpd_id")
    s = s.rename(columns={c: f"scraped_{c}" for c in s.columns if c != "oshpd_id"})

    # ---- crosswalk ----
    x = xwalk.copy()
    x["oshpd_id"] = clean_id(x["HCAI_ID"])
    x = x[x["oshpd_id"].notna()].drop_duplicates("oshpd_id")
    x["ccn"] = clean_id(x["CCN"], 6)
    x = x[["oshpd_id", "ccn", "FACNAME"]].rename(columns={"FACNAME": "crosswalk_facname"})

    # ---- CMS ----
    if not cms.empty and "Facility ID" in cms:
        c = cms.copy()
        c["ccn"] = clean_id(c["Facility ID"], 6)
        c = c[c["ccn"].notna()].drop_duplicates("ccn").drop(columns=["Facility ID"])
        c = c.rename(columns={col: f"cms_{snake(col)}" for col in c.columns if col != "ccn"})
    else:
        c = pd.DataFrame(columns=["ccn"])

    ids = pd.DataFrame({"oshpd_id": pd.concat([wide["oshpd_id"], s["oshpd_id"]]).dropna().unique()})
    merged = (ids.merge(info, on="oshpd_id", how="left")
                 .merge(s, on="oshpd_id", how="left")
                 .merge(x, on="oshpd_id", how="left")
                 .merge(c, on="ccn", how="left")
                 .merge(wide, on="oshpd_id", how="left")
                 .merge(state, left_on="year", right_index=True, how="left"))
    merged["year"] = merged["year"].astype("Int64")
    return merged


def enrich(m: pd.DataFrame) -> pd.DataFrame:
    """Add tidy, typed columns the dashboard uses."""
    m = m.copy()
    csec = find_col(m, "cesarean", "_rate")
    vbac = find_col(m, "vbac", "_rate")
    csec_n = find_col(m, "cesarean", "_count")

    m["name"] = (text(m, "scraped_hospital_name").fillna(text(m, "hcai_hospital"))
                 .fillna(text(m, "crosswalk_facname")).fillna(text(m, "cms_facility_name")))
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
    addr_parts = [text(m, "cms_address"), text(m, "cms_city_town"),
                  text(m, "cms_state").fillna("CA"), text(m, "cms_zip_code")]
    m["address"] = [", ".join(str(p) for p in parts if pd.notna(p) and str(p).strip())
                    if pd.notna(parts[0]) else None for parts in zip(*addr_parts)]
    m["directions"] = [
        "https://www.google.com/maps/dir/?api=1&destination="
        + urllib.parse.quote_plus(a if a else f"{n}, California")
        for a, n in zip(m["address"], m["name"])]

    # a hospital "delivers babies" if the scraper says so, or it has birth data
    births = (m["csec_count"].fillna(0) > 0) | m["ntsv_pct"].notna() | m["csec_rate"].notna()
    m["delivers"] = m["maternity"].fillna(False).astype(bool) | births
    m["latitude"] = pd.to_numeric(m["latitude"], errors="coerce")
    m["longitude"] = pd.to_numeric(m["longitude"], errors="coerce")
    return m


# =====================================================================
# Location helpers
# =====================================================================
@st.cache_data(ttl=86400)
def zip_to_latlon(zipcode: str) -> tuple[float, float] | None:
    try:
        r = requests.get(f"https://api.zippopotam.us/us/{zipcode}", timeout=10)
        if r.status_code != 200:
            return None
        p = r.json()["places"][0]
        return float(p["latitude"]), float(p["longitude"])
    except Exception:
        return None


def miles_between(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = (np.sin((lat2 - lat1) / 2) ** 2
         + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2)
    return 3958.8 * 2 * np.arcsin(np.sqrt(a))


# =====================================================================
# Small display helpers
# =====================================================================
def pct(v) -> str:
    return f"{v:.1f}%" if pd.notna(v) else "no data"


def yes_no(v, yes="Yes", no="No") -> str:
    return "Unknown" if pd.isna(v) else (yes if bool(v) else no)


def stars_txt(v) -> str:
    return "Not rated" if pd.isna(v) else "★" * int(v) + "☆" * (5 - int(v))


def is_true(v) -> bool:
    return bool(pd.notna(v) and bool(v))


def is_false(v) -> bool:
    return bool(pd.notna(v) and not bool(v))


def badges(r) -> str:
    out = []
    if is_true(r.get("birthing_friendly")):
        out.append("🏅 Birthing-friendly (CMS)")
    if is_true(r.get("vbac_available")):
        out.append("✅ VBAC routinely available")
    if pd.notna(r.get("midwife_pct")) and r["midwife_pct"] > 0:
        out.append(f"👩‍⚕️ Midwives deliver {r['midwife_pct']:.0f}% of births")
    if is_true(r.get("has_er")):
        out.append("🚑 24/7 emergency room")
    return " · ".join(out)


def summary_sentences(r) -> list[str]:
    """Plain-language summary of one hospital-year row."""
    lines = []
    yr = f" in {int(r['year'])}" if pd.notna(r.get("year")) else ""
    if pd.notna(r["csec_rate"]):
        cmp = ""
        if pd.notna(r["csec_state"]):
            diff = r["csec_rate"] - r["csec_state"]
            word = "higher than" if diff > 0.5 else "lower than" if diff < -0.5 else "about the same as"
            cmp = f", {word} the California average of {r['csec_state']:.1f}%"
        lines.append(f"About **{r['csec_rate']:.0f} in 100** low-risk births here were C-sections{yr}{cmp}.")
        if r["csec_rate"] <= TARGET_CSEC:
            lines.append(f"That meets the national goal of {TARGET_CSEC}% or lower.")
        else:
            lines.append(f"The national goal is {TARGET_CSEC}% or lower.")
    else:
        lines.append("No C-section rate is reported for this hospital.")
    if pd.notna(r["vbac_rate"]) or pd.notna(r["vbac_pct"]):
        v = r["vbac_rate"] if pd.notna(r["vbac_rate"]) else r["vbac_pct"]
        lines.append(f"For people who had a C-section before, **{v:.0f}%** had a vaginal birth (VBAC) here.")
    if is_false(r.get("vbac_available")):
        lines.append("This hospital does **not** routinely offer VBAC.")
    if pd.notna(r["midwife_pct"]):
        lines.append(f"Certified nurse-midwives attended **{r['midwife_pct']:.0f}%** of births.")
    return lines


def compare_chart(r) -> alt.Chart | None:
    """Hospital vs California average vs national goal, one bar group per measure."""
    rows = []
    if pd.notna(r["csec_rate"]):
        rows += [("C-section (low-risk)", "This hospital", r["csec_rate"]),
                 ("C-section (low-risk)", "California average", r["csec_state"]),
                 ("C-section (low-risk)", "National goal", TARGET_CSEC)]
    v = r["vbac_rate"] if pd.notna(r["vbac_rate"]) else r["vbac_pct"]
    if pd.notna(v):
        rows += [("VBAC rate", "This hospital", v),
                 ("VBAC rate", "California average", r["vbac_state"])]
    if pd.notna(r["midwife_pct"]):
        rows += [("Births by midwives", "This hospital", r["midwife_pct"])]
    df = pd.DataFrame(rows, columns=["Measure", "Who", "Percent"]).dropna()
    if df.empty:
        return None
    return alt.Chart(df).mark_bar().encode(
        y=alt.Y("Who:N", title=None, sort=["This hospital", "California average", "National goal"]),
        x=alt.X("Percent:Q", title="%"),
        color=alt.Color("Who:N", legend=None,
                        scale=alt.Scale(domain=["This hospital", "California average", "National goal"],
                                        range=["#2a55c0", "#9aa8bb", "#22784d"])),
        row=alt.Row("Measure:N", title=None, header=alt.Header(labelAngle=0, labelAlign="left")),
        tooltip=["Measure", "Who", alt.Tooltip("Percent:Q", format=".1f")],
    ).properties(height=alt.Step(22), width=420)


# =====================================================================
# Page sections
# =====================================================================
def show_map(pts: pd.DataFrame, home):
    """Plotly map on OpenStreetMap tiles (no token, loads fast, clearly visible)."""
    pts = pts.dropna(subset=["latitude", "longitude"]).copy()
    if pts.empty:
        st.info("None of these hospitals have map coordinates.")
        return

    rate, state = pts["csec_rate"], pts["csec_state"]
    pts["C-section rate"] = np.where(rate.isna(), "No rate reported",
                            np.where(rate > state, "Above CA average", "At or below CA average"))
    map_data = pd.DataFrame({
        "Hospital": pts["name"].fillna("").astype(str),
        "County": pts["county"].fillna("").astype(str),
        "lat": pts["latitude"].astype(float),
        "lon": pts["longitude"].astype(float),
        "C-section rate": pts["C-section rate"],
        "Rate": rate.map(pct),
        "CA average": state.map(pct),
        "Rating": pts["stars"].map(stars_txt),
    })

    center = ({"lat": home[0], "lon": home[1]} if home else
              {"lat": map_data["lat"].mean(), "lon": map_data["lon"].mean()})
    zoom = 9 if home else (10 if len(map_data) < 5 else 5)
    common = dict(lat="lat", lon="lon", color="C-section rate", hover_name="Hospital",
                  hover_data={"County": True, "Rate": True, "CA average": True, "Rating": True,
                              "lat": False, "lon": False, "C-section rate": False},
                  color_discrete_map=MAP_COLORS, category_orders={"C-section rate": list(MAP_COLORS)},
                  zoom=zoom, center=center, height=560)

    if hasattr(px, "scatter_map"):                 # plotly >= 5.24 (MapLibre)
        fig = px.scatter_map(map_data, map_style="open-street-map", **common)
        home_trace = go.Scattermap
    else:                                          # older plotly
        fig = px.scatter_mapbox(map_data, mapbox_style="open-street-map", **common)
        home_trace = go.Scattermapbox
    fig.update_traces(marker={"size": 13, "opacity": 0.9})

    if home:
        fig.add_trace(home_trace(lat=[home[0]], lon=[home[1]], mode="markers",
                                 marker={"size": 16, "color": "black"},
                                 name="Your ZIP", hovertext=["Your ZIP"], hoverinfo="text"))

    fig.update_layout(margin={"l": 0, "r": 0, "t": 0, "b": 0},
                      legend={"orientation": "h", "y": 1.02, "x": 0, "title": None})
    st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True})


def hospital_card(r):
    with st.container(border=True):
        top = st.columns([3, 1])
        dist = f" · {r['miles']:.1f} mi" if "miles" in r and pd.notna(r.get("miles")) else ""
        top[0].markdown(f"**{r['name']}**  \n{r['county'] or ''}{dist}")
        top[1].markdown(f"C-section **{pct(r['csec_rate'])}**  \n{stars_txt(r['stars'])}")
        b = badges(r)
        if b:
            st.caption(b)


def profile(r, history: pd.DataFrame):
    st.header(r["name"])
    b = badges(r)
    if b:
        st.markdown(b)

    c1, c2, c3 = st.columns(3)
    c1.metric("Low-risk C-section rate", pct(r["csec_rate"]),
              delta=None if pd.isna(r["csec_rate"]) or pd.isna(r["csec_state"])
              else f"{r['csec_rate'] - r['csec_state']:+.1f} vs CA",
              delta_color="inverse")
    c2.metric("Overall rating (CMS)", stars_txt(r["stars"]))
    c3.metric("VBAC routinely offered", yes_no(r["vbac_available"]))

    st.subheader("In plain words")
    for line in summary_sentences(r):
        st.markdown(f"- {line}")

    st.subheader("How does it compare?")
    chart = compare_chart(r)
    if chart is not None:
        st.altair_chart(chart, use_container_width=False)
        st.caption("For C-sections, lower is generally better for low-risk births. "
                   "For VBAC, higher means more people who wanted a vaginal birth after a "
                   "C-section were able to have one.")
    else:
        st.info("No comparable rates reported for this hospital.")

    trend = history.dropna(subset=["year", "csec_rate"]).sort_values("year")
    if len(trend) > 1:
        st.subheader("Getting better or worse?")
        t = pd.concat([
            trend[["year", "csec_rate"]].rename(columns={"csec_rate": "Percent"}).assign(Who="This hospital"),
            trend[["year", "csec_state"]].rename(columns={"csec_state": "Percent"}).assign(Who="California average"),
        ]).dropna()
        line = alt.Chart(t).mark_line(point=True).encode(
            x=alt.X("year:O", title="Year"),
            y=alt.Y("Percent:Q", title="Low-risk C-section rate (%)", scale=alt.Scale(zero=False)),
            color=alt.Color("Who:N", scale=alt.Scale(range=["#2a55c0", "#9aa8bb"]),
                            legend=alt.Legend(orient="bottom", title=None)),
            tooltip=["year", "Who", alt.Tooltip("Percent:Q", format=".1f")])
        goal = alt.Chart(pd.DataFrame({"g": [TARGET_CSEC]})).mark_rule(
            strokeDash=[4, 4], color="#22784d").encode(y="g:Q")
        st.altair_chart(line + goal, use_container_width=True)
        first, last = trend.iloc[0], trend.iloc[-1]
        change = last["csec_rate"] - first["csec_rate"]
        word = "down" if change < -0.5 else "up" if change > 0.5 else "about flat"
        st.caption(f"From {int(first['year'])} to {int(last['year'])} the rate went {word} "
                   f"({first['csec_rate']:.1f}% → {last['csec_rate']:.1f}%). Dashed line = national goal.")

    st.subheader("Contact & directions")
    st.markdown(f"📍 {r['address'] or 'Address not available'}")
    if pd.notna(r["phone"]):
        st.markdown(f"📞 {r['phone']}")
    st.link_button("Get directions", r["directions"])


def compare_section(hosp: pd.DataFrame):
    st.subheader("Compare up to 3 hospitals")
    names = hosp["name"].dropna().sort_values().unique().tolist()
    # drop picks that the current filters no longer include
    st.session_state["f_compare"] = [p for p in st.session_state.get("f_compare", []) if p in names]
    picks = st.multiselect("Choose hospitals", names, max_selections=3,
                           placeholder="Start typing a hospital name", key="f_compare")
    if not picks:
        st.info("Pick two or three hospitals to see them side by side.")
        return
    sel = hosp.drop_duplicates("name").set_index("name").loc[picks]
    table = pd.DataFrame({
        "Low-risk C-section rate": sel["csec_rate"].map(pct),
        "California average": sel["csec_state"].map(pct),
        "VBAC rate": sel["vbac_rate"].fillna(sel["vbac_pct"]).map(pct),
        "VBAC routinely offered": sel["vbac_available"].map(yes_no),
        "Births by midwives": sel["midwife_pct"].map(pct),
        "Birthing-friendly (CMS)": sel["birthing_friendly"].map(yes_no),
        "Overall rating": sel["stars"].map(stars_txt),
        "24/7 emergency room": sel["has_er"].map(yes_no),
        "Distance": sel["miles"].map(lambda v: f"{v:.1f} mi" if pd.notna(v) else "—")
        if "miles" in sel else "—",
        "Phone": sel["phone"].fillna("—"),
        "Address": sel["address"].fillna("—"),
    }).T
    st.dataframe(table, use_container_width=True)

    bars = []
    for n, r in sel.iterrows():
        bars += [(n, "C-section (low-risk)", r["csec_rate"]),
                 (n, "VBAC", r["vbac_rate"] if pd.notna(r["vbac_rate"]) else r["vbac_pct"]),
                 (n, "Births by midwives", r["midwife_pct"])]
    bdf = pd.DataFrame(bars, columns=["Hospital", "Measure", "Percent"]).dropna()
    if not bdf.empty:
        st.altair_chart(alt.Chart(bdf).mark_bar().encode(
            x=alt.X("Percent:Q", title="%"),
            y=alt.Y("Hospital:N", title=None),
            color=alt.Color("Hospital:N", legend=None),
            row=alt.Row("Measure:N", title=None, header=alt.Header(labelAngle=0, labelAlign="left")),
            tooltip=["Hospital", "Measure", alt.Tooltip("Percent:Q", format=".1f")],
        ).properties(height=alt.Step(22), width=420))
    cols = st.columns(len(picks))
    for col, (n, r) in zip(cols, sel.iterrows()):
        col.link_button(f"Directions: {n[:28]}", r["directions"], use_container_width=True)


def checklist_section():
    st.subheader("Questions to ask on your hospital tour")
    st.write("Tick the ones you want to ask, then download your list to bring along.")
    chosen = []
    for g, (group, qs) in enumerate(TOUR_QUESTIONS.items()):
        st.markdown(f"**{group}**")
        for i, q in enumerate(qs):
            if st.checkbox(q, key=f"q_{g}_{i}"):
                chosen.append(q)
    if chosen:
        st.download_button("Download my questions",
                           "My hospital tour questions\n\n" + "\n".join(f"[ ] {q}" for q in chosen),
                           "hospital_tour_questions.txt", "text/plain")


# every dashboard control and its starting value (used by "Clear all selections")
DEFAULTS = {"f_zip": "", "f_radius": 25, "f_delivers": True, "f_vbac": False,
            "f_midwife": False, "f_min_midwife": 5, "f_bf": False, "f_er": False,
            "f_stars": "Any", "f_year": "Latest available", "f_name": "", "f_compare": []}


def init_state():
    for k, v in DEFAULTS.items():
        st.session_state.setdefault(k, v)


def clear_selections():
    """Reset every filter, search box, comparison and checklist — data is NOT re-downloaded."""
    for k, v in DEFAULTS.items():
        st.session_state[k] = v
    for k in list(st.session_state):
        if k.startswith("q_") or k == "f_profile":
            del st.session_state[k]


@st.cache_data(ttl=3600, show_spinner=False)
def load_guide_data() -> tuple[pd.DataFrame, list[str], str | None]:
    """Download + merge everything once per hour; every click after that is instant."""
    data, files = retrieve_data_from_gcs(service_account_file_path, project_id,
                                         bucket_name, FOLDER)
    if data.empty:
        return pd.DataFrame(), files, f"No data found under '{FOLDER}' in the bucket."
    xwalk, scraped = part(data, CROSSWALK_FOLDER), part(data, SCRAPED_FOLDER)
    hcai, cms = part(data, HCAI_FOLDER), part(data, CMS_FOLDER)
    missing = [n for n, d in [(CROSSWALK_FOLDER, xwalk), (SCRAPED_FOLDER, scraped),
                              (HCAI_FOLDER, hcai)] if d.empty]
    if missing:
        return (pd.DataFrame(), files,
                f"No data in: {missing}. Folders found: {sorted(data['source_folder'].unique())}")
    return enrich(merge_all(xwalk, scraped, hcai, cms)), files, None


# =====================================================================
# App
# =====================================================================
if __name__ == "__main__":
    st.set_page_config(page_title="California Birth Hospital Guide", page_icon="🤰", layout="wide")
    st.title("California Birth Hospital Guide")
    st.caption("Compare C-section and VBAC rates, midwife care and hospital ratings "
               "to help plan where to give birth.")

    init_state()
    with st.spinner("Loading hospital data…"):
        allrows, files, problem = load_guide_data()
    if problem:
        st.error(problem)
        st.stop()

    # ---------------- sidebar: what matters to you ----------------
    with st.sidebar:
        st.header("Your search")
        st.button("Clear all selections", on_click=clear_selections, use_container_width=True)
        zip_q = st.text_input("Your ZIP code", max_chars=5, placeholder="e.g. 94117", key="f_zip")
        radius = st.slider("Within (miles)", 5, 100, step=5, disabled=not zip_q, key="f_radius")

        st.header("What matters to you")
        delivers_only = st.checkbox("Delivers babies", key="f_delivers",
                                    help="Hides hospitals without a maternity unit.")
        want_vbac = st.checkbox("I had a C-section before and want to try a vaginal birth (VBAC)",
                                key="f_vbac")
        want_midwife = st.checkbox("I'd like a midwife-friendly hospital", key="f_midwife")
        min_midwife = st.slider("Midwives attend at least (%)", 1, 50,
                                disabled=not want_midwife, key="f_min_midwife")
        bf_only = st.checkbox("Birthing-friendly designation (CMS)", key="f_bf")
        er_only = st.checkbox("Has a 24/7 emergency room", key="f_er")
        min_stars = st.select_slider("Minimum overall rating", ["Any", 1, 2, 3, 4, 5], key="f_stars")

        years = sorted(allrows["year"].dropna().unique(), reverse=True)
        year_opts = ["Latest available"] + [int(y) for y in years]
        if st.session_state["f_year"] not in year_opts:
            st.session_state["f_year"] = "Latest available"
        year = st.selectbox("Data year", year_opts, key="f_year")

    # ---------------- one row per hospital ----------------
    rows = allrows if year == "Latest available" else allrows[allrows["year"] == year]
    hosp = (rows.sort_values("year", ascending=False, na_position="last")
                .drop_duplicates("oshpd_id").copy())

    home = None
    if zip_q:
        if zip_q.isdigit() and len(zip_q) == 5:
            home = zip_to_latlon(zip_q)
            if home is None:
                st.sidebar.warning(f"Couldn't find ZIP {zip_q}.")
        else:
            st.sidebar.warning("Enter a 5-digit ZIP code.")
    if home:
        hosp["miles"] = miles_between(home[0], home[1], hosp["latitude"], hosp["longitude"])

    f = hosp
    if delivers_only:
        f = f[f["delivers"]]
    if want_vbac:
        f = f[f["vbac_available"].fillna(False).astype(bool)]
    if want_midwife:
        f = f[f["midwife_pct"].fillna(0) >= min_midwife]
    if bf_only:
        f = f[f["birthing_friendly"].fillna(False).astype(bool)]
    if er_only:
        f = f[f["has_er"].fillna(False).astype(bool)]
    if min_stars != "Any":
        f = f[f["stars"].fillna(0) >= min_stars]
    if home:
        f = f[f["miles"] <= radius].sort_values("miles")
    else:
        f = f.sort_values("name")

    tab_find, tab_profile, tab_compare, tab_tour, tab_about = st.tabs(
        ["🔎 Find a hospital", "🏥 Hospital profile", "⚖️ Compare", "📝 Tour questions", "ℹ️ About the data"])

    # ---------------- Find ----------------
    with tab_find:
        name_q = st.text_input("Search by hospital name", placeholder="e.g. Kaiser, Sutter, St Rose",
                               key="f_name")
        results = f[f["name"].str.contains(name_q, case=False, na=False)] if name_q else f

        k1, k2, k3 = st.columns(3)
        k1.metric("Hospitals found", len(results))
        k2.metric("Median low-risk C-section rate", pct(results["csec_rate"].median()))
        k3.metric("Offer VBAC routinely", int(results["vbac_available"].fillna(False).astype(bool).sum()))

        if results.empty:
            st.warning("No hospitals match. Try a bigger distance or fewer filters in the sidebar.")
        else:
            show_map(results, home)
            st.markdown("#### Results" + (" (nearest first)" if home else ""))
            for _, r in results.head(25).iterrows():
                hospital_card(r)
            if len(results) > 25:
                st.caption(f"Showing 25 of {len(results)}. Narrow the search to see more.")

    # ---------------- Profile ----------------
    with tab_profile:
        options = (f if not f.empty else hosp)["name"].dropna().unique().tolist()
        if st.session_state.get("f_profile") not in options:      # filters changed
            st.session_state.pop("f_profile", None)
        pick = st.selectbox("Choose a hospital", options, key="f_profile")
        if pick:
            r = hosp[hosp["name"] == pick].iloc[0]
            history = allrows[allrows["oshpd_id"] == r["oshpd_id"]]
            profile(r, history)

    # ---------------- Compare ----------------
    with tab_compare:
        compare_section(f if not f.empty else hosp)

    # ---------------- Tour checklist ----------------
    with tab_tour:
        checklist_section()

    # ---------------- About ----------------
    with tab_about:
        st.subheader("What the numbers mean")
        st.markdown(f"""
- **Low-risk C-section rate** — HCAI's "uncomplicated cesarean delivery" rate: the share of
  low-risk births delivered by C-section. Looking only at low-risk births removes most
  high-risk cases, so hospitals can be compared more fairly. The closely related national
  goal for first-time, low-risk births (Healthy People 2030 NTSV) is **{TARGET_CSEC}% or lower**.
- **VBAC rate** — of people who had a C-section before, the share who had a vaginal birth.
- **Births by midwives** — the share of births attended by certified nurse-midwives.
- **Birthing-friendly** — a CMS designation for hospitals that take part in maternity
  quality programs and follow recommended safety practices.
- **Overall rating** — CMS's 1–5 star summary of general hospital quality (not maternity-specific).
""")
        st.warning("This guide is for information only and isn't medical advice. A hospital's rate "
                   "can be higher because it cares for more high-risk patients. Talk with your "
                   "doctor or midwife about what's right for you.")
        st.subheader("Sources")
        st.markdown("HCAI (California Department of Health Care Access and Information) · "
                    "CMS Hospital General Information · CHHS licensed-facility crosswalk · "
                    "scraped hospital maternity details.")
        h1 = allrows.drop_duplicates("oshpd_id")
        st.caption(f"{len(files)} files · {len(h1)} hospitals · "
                   f"{int(h1['delivers'].sum())} deliver babies · "
                   f"{int(h1['stars'].notna().sum())} matched to CMS")