import io

import pandas as pd 
import requests 

#current data set 
cms_url = (
    "https://data.cms.gov/provider-data/api/1/"
    "metastore/schemas/dataset/items/xubh-q36u"
)


def fetch(state="CA"):
    response = requests.get(cms_url)
    response.raise_for_status()
    data = response.json()

    csv_url = next(
        item["downloadURL"]
        for item in data["distribution"]
        if item.get("mediaType") == "text/csv"
    )

    #hospital
    response = requests.get(csv_url)
    response.raise_for_status()

    hospitals = pd.read_csv(
        io.BytesIO(response.content),
        dtype=str,
        keep_default_na=False,
    )
    hospitals.columns = hospitals.columns.str.strip()

    #state
    state_hospitals = hospitals.loc[
        hospitals["State"].str.strip().str.upper() == state.upper()
    ].copy()

    if state_hospitals.empty:
        raise ValueError(f"No {state} hospital found")

    return state_hospitals