import io
import os

import pandas as pd 
import requests 
from dotenv import load_dotenv
from storage import store_to_gcs 

load_dotenv()

service_account_key = os.getenv("GCP_SERVICE_ACCOUNT_KEY")
project_id = os.getenv("GCP_PROJECT_ID")
bucket_name = os.getenv("GCP_BUCKET_NAME")

#current data set 
cms_url = (
    "https://data.cms.gov/provider-data/api/1/"
    "metastore/schemas/dataset/items/xubh-q36u"
)

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

#california

ca_hospitals = hospitals.loc[
    hospitals["State"].str.strip().str.upper() == "CA"
].copy()

if ca_hospitals.empty:
    raise ValueError("No CA hospital found")

#csv to gcs 
store_to_gcs(
    service_account_key, 
    project_id, 
    bucket_name,
    "cms_hospitals_ca.csv",
    ca_hospitals.to_csv(index=False)
)

print (f"Uploaded {len(ca_hospitals)} CA hospitals.")