import os

from dotenv import load_dotenv

load_dotenv()
project_id = os.getenv('gcp_project_id')
vertex_ai_project_id = os.getenv('vertex_ai_project_id')
search_engine_id = os.getenv('search_engine_id')
bucket_name = os.getenv('gcp_bucket_name')
service_account_file_path = os.getenv('gcp_service_account_key')
api_server_url = os.getenv('api_service_url')

# file_name_prefix = 'job_search'