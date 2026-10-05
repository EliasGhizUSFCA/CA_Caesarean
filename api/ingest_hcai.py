import os 
import requests 
from dotenv import load_dotenv 
from storage import store_to_gcs 

load_dotenv()

service_account_key = os.getenv("GCP_SERVICE_ACCOUNT_KEY")
project_id = os.getenv("GCP_PROJECT_ID")
bucket_name = os.getenv("GCP_BUCKET_NAME")
hcai_url = os.getenv("HCAI_DATA_URL")

#download 
response = requests.get(hcai_url)
response.raise_for_status()

#store 
store_to_gcs(
    service_account_key, 
    project_id, 
    bucket_name, 
    "hcai_data.xlsx",
    response.content
)

print("Data uploaded.")