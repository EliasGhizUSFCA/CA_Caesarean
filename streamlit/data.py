# AI USE: This file was written with help from Claude Opus 5.5 (Anthropic),
# through several rounds of prompts and fixes. The prompts are listed in here 
"""
Prompt 1: Modify Streamlit App to Read From GCS
Here is our existing job-listings Streamlit application that we worked on earlier. I want to reuse the same structure for our hospital dashboard, but for now lets focus only on retrieving the data from our GCS bucket. Remove the job listing specific logic and update the data retrieval function to read the hospital dataset instead. Keep the existing authentication method and use Pandas to load the data into a dataframe. We can work on the visualizations and filters later, right now I just want to make sure we can successfully retrieve and display the data.
Prompt 2: Read All Files From Nested GCS Folders
Our GCS bucket has a main folder called hospital/, but inside that folder we have multiple subfolders containing different hospital datasets. Right now the code only reads from one location. Can we update the retrieval function to list all the blobs under the hospital/ prefix and read the JSON files from all the nested folders? Since GCS uses object prefixes rather than actual directories, we should be able to iterate through the blobs using the storage client. Make sure we are not missing files from any subfolder and handle the JSON records properly when converting them into dataframes.
Prompt 3: Fix Sidebar Folder Filtering
The sidebar is showing the different folders from our GCS bucket, but selecting a folder doesnt actually change the data displayed in the table. Can you check how we are applying the selected folder to the dataframe? I think we need to keep track of which folder each record came from when loading the JSON files, then use that information to filter the dataframe based on the sidebar selection. Make sure the table updates when the selection changes without having to download the files again.
Prompt 4: Keep the Existing Code Structure
I noticed the code is starting to look different from our original job-listings Streamlit application. Can you keep the same overall structure and coding style that we used before? I dont want to introduce new classes or complicated design patterns for something we can do with the existing functions. Try to reuse the same approach for retrieving data, creating the dataframe, and displaying the results. Only modify what is necessary for the hospital dataset.
Prompt 5: Decide Where to Perform Data Cleaning and Joins
We now have multiple hospital datasets coming from different sources, and eventually we need to combine them into one dataset for the dashboard. Im trying to decide whether we should load all the raw files into Streamlit and perform the cleaning and joins there, or process everything on the server side before saving a merged dataset back to GCS. Since Streamlit reruns when users interact with widgets, im concerned that joining multiple datasets in the dashboard might affect performance. Which approach would be better in terms of processing time, maintainability, and avoiding repeated transformations? Also consider that our data is not updated very frequently.
Prompt 6: Join Scraped Hospital Data With Crosswalk
Lets start combining our hospital datasets. We have the scraped hospital information and a crosswalk dataset that contains identifiers used across different healthcare data sources. I want to join these two datasets so we can match the scraped hospital records with the corresponding identifiers in the crosswalk. Check the available columns and make sure the hospital IDs have consistent data types before merging. Use Pandas merge() and preserve the hospital information from the scraper while adding the matching identifiers from the crosswalk. Also check for unmatched records and duplicates so we can see if the join is working correctly.
Prompt 7: Fix UnicodeDecodeError When Reading JSON
Im getting a UnicodeDecodeError: 'utf-8' codec can't decode bytes when trying to read one of the files from GCS. All the files we are working with are supposed to be JSON, so we dont need to support CSV or other formats. Can you check how the blob content is being downloaded and decoded before passing it to json.loads()? Maybe some files have different encoding or there are objects in the bucket that are not actual JSON files. Add some error handling so we can identify which file is causing the issue instead of having the entire data loading process fail.
Prompt 8: Add HCAI Cesarean and VBAC Data
Now that we have the scraped hospital data joined with the crosswalk, I want to include the HCAI dataset containing cesarean delivery and VBAC information. Use the hospital identifier from HCAI to match the corresponding records in our existing merged dataframe. Make sure we preserve the reporting year because we will need it later for trend analysis. Also check if HCAI has multiple records for the same hospital across different years, since we dont want the join to create unexpected duplicates. Keep the cesarean and VBAC metrics separate and make sure missing values are handled correctly.
Prompt 9: Merge CMS, Crosswalk, HCAI, and Scraped Data
Here are sample records from the four datasets we are using: CMS, the hospital crosswalk, HCAI, and our scraped hospital information. I want to combine them into one dataset that we can use for the Streamlit dashboard.
Based on the identifiers, lets use the crosswalk as the main reference for matching hospitals across sources. The HCAI dataset uses OSHPD_ID, and our scraped data uses oshpd_id, which should match the HCAI_ID column in the crosswalk. After matching those records, use the crosswalk CCN to join the CMS data using its Facility ID column.
Before merging, normalize the identifier columns so differences in data types or formatting dont prevent valid matches. Also be careful with leading zeros in CMS identifiers. Check the join cardinality because some datasets might contain multiple records per hospital, especially HCAI with different reporting years. I want to preserve the available hospital information without creating duplicate rows from incorrect joins. After merging, show how many hospitals matched across the sources and how many records were left unmatched.
Prompt 10: Fix Missing Latitude and Longitude After Merge
I noticed the original HCAI dataset has latitude and longitude columns, but those values are missing from our final merged dataframe. Can you check whether the coordinates are being dropped during column selection or if the merge is creating duplicate columns with suffixes like _x and _y? Also verify that the hospital identifiers are matching correctly between HCAI and the crosswalk. We need the coordinates for the hospital map, so make sure the final dataset retains valid latitude and longitude values without changing the existing join logic unnecessarily.
Prompt 11: Remove Hospitals With Missing Information
The merged dataset contains some hospitals that dont have much useful information for our dashboard. Can we filter out hospitals that have no relevant maternity care data? I dont want to remove records just because one column is missing, but hospitals with no cesarean rates, VBAC information, or other meaningful maternity indicators probably shouldnt appear in the main hospital list. Check the available columns and create a filtering condition based on whether the hospital has at least one useful maternity-related metric. Make sure missing values like None, NaN, or empty strings are handled properly.
Prompt 12: Fix Hospitals Appearing Without Cesarean Data
Adventist Health Dameron Hospital is still showing in the hospital list even though it doesnt have any cesarean delivery data. Can you check why this hospital is passing our filtering condition? I think the current logic might be keeping hospitals just because they have a CMS star rating, even when they dont have any maternity-related metrics. Update the condition so a CMS star rating alone is not enough for a hospital to appear in the list. Also, for hospitals with multiple reporting years, make sure we display the most recent year that actually has a valid cesarean rate rather than just selecting the latest year in the dataset, which might have a missing value. Keep the historical records available because we will need them for trend analysis.

Loading, cleaning and merging the hospital data from the GCS bucket.

Folders read from the bucket (hospital/):
    hcai/               cesarean and VBAC rates by hospital and year
    scraped-hospitals/  scraped maternity details
    crosswalk/          HCAI_ID to CCN crosswalk
    cms/                CMS hospital general information
"""
import json
import re
import urllib.parse

import numpy as np
import pandas as pd
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


def drop_empty_hospitals(m: pd.DataFrame) -> pd.DataFrame:
    """Remove hospitals that have no maternity information.

    A CMS star rating alone is not enough, because it is about the whole
    hospital, not about giving birth there.
    """
    info_cols = ["csec_rate", "vbac_rate", "ntsv_pct", "vbac_pct", "midwife_pct",
                 "birthing_friendly", "vbac_available"]
    has_info = m[info_cols].notna().any(axis=1)
    # keep every year of a hospital if any of its rows has information
    keep = m.loc[has_info, "oshpd_id"].unique()
    return m[m["oshpd_id"].isin(keep)].reset_index(drop=True)


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

    merged = enrich(merge_all(xwalk, scraped, hcai, cms))
    return drop_empty_hospitals(merged), files, None


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