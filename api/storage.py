import os
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
                 data: bytes,)-> None:    
    credentials = service_account.Credentials.from_service_account_file(service_account_key)
    client = storage.Client(project=project_id,
                            credentials=credentials)
    bucket = client.bucket(bucket_name)
    file = bucket.blob(file_name)
    file.upload_from_string(data)