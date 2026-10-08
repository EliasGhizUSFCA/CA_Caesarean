import os
from datetime import date

from dotenv import load_dotenv 
from google.cloud import storage
from google.oauth2 import service_account

load_dotenv()

service_account_key = os.getenv("GCP_SERVICE_ACCOUNT_KEY")
project_id = os.getenv("GCP_PROJECT_ID")
bucket_name = os.getenv("GCP_BUCKET_NAME")


def store_to_gcs(service_account_key: str,
                 project_id: str,
                 bucket_name: str,
                 file_name: str,
                 data: str,)-> None:    
    credentials = service_account.Credentials.from_service_account_file(service_account_key)
    client = storage.Client(project=project_id,
                            credentials=credentials)
    bucket = client.bucket(bucket_name)
    file = bucket.blob(file_name)
    file.upload_from_string(data)


def save_file(data, dataset: str, file_name: str, partition: str = "") -> str:
    parts = [dataset, partition, date.today().strftime("%Y-%m"), file_name] #saves new file every month
    path = "/".join(p for p in parts if p)
    store_to_gcs(service_account_key, project_id, bucket_name, path, data)
    return path

def save_dataframe(df, dataset: str, partition: str = "") -> str:
    return save_file(df.to_csv(index=False), dataset, "data.csv", partition)