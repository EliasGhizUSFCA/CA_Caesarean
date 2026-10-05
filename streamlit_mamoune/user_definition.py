"""Server-side settings; no GCP credentials needed by the frontend."""
import os
from pathlib import Path
from dotenv import load_dotenv
ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT.parent / '.env')
load_dotenv(ROOT / '.env')
API_SERVICE_URL = os.getenv('API_SERVICE_URL', os.getenv('api_service_url', 'http://localhost:8000')).rstrip('/')
FILTERS_PATH = os.getenv('API_FILTERS_PATH', '/filters')
HOSPITALS_PATH = os.getenv('API_HOSPITALS_PATH', '/hospitals')
API_TOKEN = os.getenv('API_TOKEN', '')
DEFAULT_MODE = os.getenv('DATA_MODE', 'demo').lower()
METRICS = {
    'cesarean_rate': 'C-section rate',
    'primary_cesarean_rate': 'Primary C-section rate',
    'ntsv_cesarean_rate': 'NTSV C-section rate',
    'vbac_rate': 'VBAC rate',
}
