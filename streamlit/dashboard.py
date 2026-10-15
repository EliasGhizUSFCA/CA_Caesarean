import io
import json

import pandas as pd
import streamlit as st
from google.cloud import storage
from google.oauth2 import service_account

from user_definition import (bucket_name, project_id,
                             service_account_file_path)

FOLDER = "hospital/"                    # top-level folder; everything inside it is read
CROSSWALK_FOLDER = "crosswalk"          # hospital/crosswalk/...
SCRAPED_FOLDER = "scraped-hospitals"    # hospital/scraped-hospitals/...

# likely join columns, checked in this order (case-insensitive)
KEY_GUESSES = [("CCN", "Facility ID"), ("CCN", "CCN"), ("HCAI_ID", "OSHPD_ID"),
               ("HCAI_ID", "HCAI_ID"), ("NPI", "NPI"), ("FACNAME", "Facility Name")]


@st.cache_data(ttl=3600)          # download once, reuse on every click (refresh hourly)
def retrieve_data_from_gcs(service_account_key: str,
                           project_id: str,
                           bucket_name: str,
                           folder: str) -> tuple[pd.DataFrame, list[str]]:
    """
    Read every .csv / .json file under `folder` (including all subfolders)
    and combine them into one DataFrame.
    Returns (data, list_of_files_read).
    """
    credentials = service_account.Credentials.from_service_account_file(
        service_account_key)
    client = storage.Client(project=project_id, credentials=credentials)
    bucket = client.bucket(bucket_name)

    frames, files_read = [], []
    for blob in bucket.list_blobs(prefix=folder):      # recursive by default
        name = blob.name
        if name.endswith("/"):                         # empty "folder" marker
            continue

        if name.endswith(".csv"):
            df = pd.read_csv(io.StringIO(blob.download_as_text()), dtype=str)
        elif name.endswith(".json"):
            df = pd.json_normalize(json.loads(blob.download_as_text())).astype(str)
        else:
            continue                                   # skip other file types

        relative = name[len(folder):]
        df["source_folder"] = "/".join(relative.split("/")[:-1]) or "(root)"
        df["source_file"] = relative.split("/")[-1]

        frames.append(df)
        files_read.append(name)

    data = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return data, files_read


def part(data: pd.DataFrame, folder: str) -> pd.DataFrame:
    """Rows from one top-level subfolder, with its all-empty columns removed."""
    rows = data[data["source_folder"].str.split("/").str[0] == folder]
    return rows.replace({"nan": None, "None": None, "": None}).dropna(axis=1, how="all")


def clean_key(col: pd.Series) -> pd.Series:
    """Make IDs comparable: trim, upper-case, drop '.0', pad numeric CCNs to 6 digits."""
    s = col.astype(str).str.strip().str.upper().str.replace(r"\.0$", "", regex=True)
    return s.where(~s.str.fullmatch(r"\d{1,6}"), s.str.zfill(6))


def guess_keys(xwalk: pd.DataFrame, scraped: pd.DataFrame) -> tuple[str, str]:
    lower_x = {c.lower(): c for c in xwalk.columns}
    lower_s = {c.lower(): c for c in scraped.columns}
    for x, s in KEY_GUESSES:
        if x.lower() in lower_x and s.lower() in lower_s:
            return lower_x[x.lower()], lower_s[s.lower()]
    common = [c for c in xwalk.columns if c in scraped.columns
              and c not in ("source_folder", "source_file")]
    return (common[0], common[0]) if common else (xwalk.columns[0], scraped.columns[0])


if __name__ == "__main__":
    st.title("Caesarean Project Dashboard")

    data, files = retrieve_data_from_gcs(service_account_file_path,
                                         project_id, bucket_name, FOLDER)
    if data.empty:
        st.warning(f"No .csv/.json files found under '{FOLDER}'.")
        st.stop()

    xwalk = part(data, CROSSWALK_FOLDER)
    scraped = part(data, SCRAPED_FOLDER)
    if xwalk.empty or scraped.empty:
        st.error(f"Need both '{CROSSWALK_FOLDER}' and '{SCRAPED_FOLDER}'. "
                 f"Folders found: {sorted(data['source_folder'].unique())}")
        st.stop()

    # ---------- sidebar: choose how to join ----------
    with st.sidebar:
        st.header("Join settings")
        gx, gs = guess_keys(xwalk, scraped)
        x_cols = [c for c in xwalk.columns if not c.startswith("source_")]
        s_cols = [c for c in scraped.columns if not c.startswith("source_")]
        x_key = st.selectbox("Crosswalk column", x_cols, index=x_cols.index(gx) if gx in x_cols else 0)
        s_key = st.selectbox("Scraped-hospitals column", s_cols, index=s_cols.index(gs) if gs in s_cols else 0)
        how = st.radio("Keep", ["Every scraped hospital (left)", "Only matches (inner)"])

        st.caption(f"{len(files)} files read from the bucket")
        if st.button("Reload from bucket"):
            st.cache_data.clear()
            st.rerun()

    # ---------- join ----------
    left = scraped.drop(columns=["source_folder", "source_file"]).copy()
    right = (xwalk.drop(columns=["source_folder", "source_file"])
                  .assign(_key=lambda d: clean_key(d[x_key]))
                  .drop_duplicates("_key"))                   # one crosswalk row per ID
    left["_key"] = clean_key(left[s_key])

    joined = left.merge(right, on="_key", how="left" if how.startswith("Every") else "inner",
                        suffixes=("", "_crosswalk"), indicator=True)
    matched = int((joined["_merge"] == "both").sum())
    joined = joined.drop(columns=["_key", "_merge"])

    # ---------- main area ----------
    c1, c2, c3 = st.columns(3)
    c1.metric("Scraped hospitals", len(left))
    c2.metric("Crosswalk rows", len(right))
    c3.metric("Matched", f"{matched} ({matched / max(len(left), 1):.0%})")
    if matched == 0:
        st.warning("Nothing matched — try a different pair of columns in the sidebar.")

    st.subheader("Joined data")
    st.dataframe(joined, hide_index=True)
    st.download_button("Download joined CSV", joined.to_csv(index=False),
                       "hospitals_joined.csv", "text/csv")

    with st.expander("Raw tables"):
        st.write("Crosswalk", xwalk.head(20))
        st.write("Scraped hospitals", scraped.head(20))