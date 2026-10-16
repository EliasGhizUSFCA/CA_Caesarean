# CA_Caesarean
C-section rates vary greatly from one California hospital to the next. By combining our data from a veriety of sources. We created a dashboard tool to help new families compare hospitals and decide where to deliver their babies. This can be used by anyone expecting to deliver in California and will help families identify the best most trustworthy hospitals.

## Team Members

| Name | GitHubID | Role / Focus |
| --- | --- | --- |
| Chloe Buhl | cjbuhl | Crosswalk, Join Data, Data Cleaning|
| Mary Kim | MaryHCDS | FastAPI, Report, Streamlit, Data Cleaning|
| Elias Ghiz | EliasGhizUSFCA | README, Web Scraping, Data Cleaning |
| Narayan Poudel | naryan | FastAPI, GCP connection, Data Cleaning|
| Mammoune El Boukfaoui | melboukfaoui | Streamlit |

---

## Problem Statement
Cesarean delivery is typically framed as a clinical decision made for an individual patient. However, c-section rates in the United States vary wildly across hospitals, even among fairly low risk births. Our project would seek to quantify that gap for hospitals in California with visualizations that utilize available observed hospital data. The final product would be a easy to read dashbord where a user could select a county and see available hospital's, c-section, NTSV (Nulliparous, Term, Singleton, Vertex) c-section and VBAC (Vaginal Birth After Cesarean) rates side by side, filtered by year and hospital ownership type. This deliverable could serve expectant parents choosing a hospital for delivery and quality committees who want a more local benchmark than just the statewide average.



---

## Data Sources and Integration Goal
- With the following data we want to integrate it onto a dashboard where it is very easy to identify certain hospitals. All of the data provides different information, including hospital delivery rates, facility characteristics, and maternity care quality measures. We created a dashboard where expecting families can easily access and compare hospital information.

### Sources
| # | Source & Link | Method | What it contains | Update frequency | Access requirements |
| --- | --- | --- | --- | --- | --- |
| 1 | [HCAI Utilization Rates for Selected Medical Procedures in California Hospitals](https://data.chhs.ca.gov/dataset/utilization-rates-for-selected-medical-procedures-in-california-hospitals) | File | About 3,300 rows, one per hospital per year per procedure: year, county, hospital, OSHPD_ID, procedure, count, rate per 100 deliveries, and latitude/longitude. We keep Cesarean, Primary Cesarean, and VBAC. Covers YEAR–YEAR, all California licnsed hospitals. | Annually last updated 10/10/2025 | None|
| 2 | [CMS Hospital General Information](https://data.cms.gov/provider-data/dataset/xubh-q36u) | API | About 5,400 rows, one per Medicare registered hospital in the U.S. but we will filter for CA. We use CCN, name, address, ZIP, county, hospital type, ownership, emergency services, birthing friendly designation, and overall star rating. | Quarterly | None; no published rate limit |
| 3 | [CalHHS Facility Crosswalk](https://data.chhs.ca.gov/dataset/licensed-facility-crosswalk) | CSV, grabbed at runtime | Connects HCAI_ID to CCN and NPI. Filter to hospitals only (General Acute Care Hospital 434, Acute Psychiatric Hospital 125, Chemical Dependency Recovery Hospital 10, Alternative Birthing Center 8); drop closed facilities using license/ASPEN status; determine a rule for parent/child facilities that share a CCN. | NA | None |
| 4 | [Cal Hospital Compare](https://calhospitalcompare.org/wp-content/provider_list.txt) | Scraping | Quality measures not covered by HCAI, scraped only for hospitals HCAI flags as delivering. Joins on OSHPD_ID (used in each URL). We use NTSV c-section rate, VBAC rate and availability, CNM delivery rate, episiotomy rate, exclusive human milk feeding, and Baby Friendly status. Values are strings that need stripping and casting; missing maternity data is expected for non-delivering hospitals, and all-zero rows for delivering hospitals get flagged for review. | NA | None |


Note: If we need a key, say which environment variable holds it and make sure that variable also appears in the .env_template

### Integration Goal
- Our integration goal is to combine data from multiple healthcare data sources into one dashboard that helps expecting families make informed decisions about where to deliver their babys in California.

---

## Setup Instructions (Locally)
### 1. Clone the Repository

```bash
git clone https://github.com/EliasGhizUSFCA/CA_Caesarean.git
cd CA_Caesarean
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r api/requirements.txt
pip install -r streamlit/requirements.txt
```

### 3. Configure Environment Variables

```bash
cp .env_template .env
```

Update `.env` with the required configuration values.

### 4. Start FastAPI

```bash
cd api
uvicorn main:app --reload
```

FastAPI must run from inside `api/` because the modules use flat imports.

- **Swagger UI:** http://127.0.0.1:8000/docs
- **ReDoc:** http://127.0.0.1:8000/redoc

### 5. Start Streamlit

Open a separate terminal from the repository root:

```bash
source .venv/bin/activate
streamlit run streamlit/dashboard.py
```

**Dashboard:** http://localhost:8501

### 6. Populate the Google Cloud Storage Bucket

From http://127.0.0.1:8000/docs, run each collector once.

| Endpoint | Runtime | GCS Path |
|----------|---------|----------|
| `POST /crosswalk` | ~10s | `hospital/crosswalk/{date}/data.xlsx` |
| `POST /hcai` | ~15s | `hospital/hcai/data.xlsx` |
| `POST /cms-hospitals` | ~30s | `hospital/cms/data.csv` |
| `POST /scrape-hospitals` | 1–2 min | `hospital/scraped-hospitals/data.json` |

1. Select the endpoint.
2. Click **Try it out**.
3. Click **Execute**.
4. Verify the response and confirm the data was saved to the GCS bucket.

### Prerequisites
- Python 3.11+
- Docker
- fastapi
- plotly
- pandas
- beautifulsoup4
- requests
- pydantic
- uvicorn
- openpxl
- A GCP service account key with access to `PROJECT_ID` / `BUCKET_NAME` / `DATASET_NAME`
- run this 'pip install -r requirements.txt'

### 1. Clone the repository
```bash
git clone https://github.com/EliasGhizUSFCA/CA_Caesarean.git
cd REPO
```

### 2. Configure environment variables

GCP_PROJECT_ID=
GCP_BUCKET_NAME=
GCP_SERVICE_ACCOUNT_KEY=
API_SERVICE_URL=
HCAI_DATA_URL=

cp. env_template .env

| Variable | Description | Example |
| --- | --- | --- |
| `GCP_PROJECT_ID` | Google Cloud project ID that is used by the application. | `ca-caesarean` |
| `GCP_BUCKET_NAME' | Google Cloud Storage bucket for collected datasets |`ca-caesarean-data` |
| `GCP_SERVICE_ACCOUNT_KEY` | Absolute path to your service account JSON file | `/Users/you/.ssh/service-account.json` |
| `HCAI_DATA_URL` | Direct download URL for the HCAI dataset (source #1) in Excel format | https://data.chhs.ca.gov/dataset/6b63ea70-aac3-4d96-bbf7-b6e0ea54039e/resource/06f75573-e5b3-4ab3-a7a7-84ab56e83965/download/2020-2024-utilization-rates-ahrq-v2025.xlsx |
| `API_SERVICE_URL` | FastAPI url that Streamlit Connects to the FastAPI | `http://127.0.0.1:8000 for local development` |




### 4. How to call your endpoint
To start the API server,
```python
cd CA_Caesarean
fastapi run api/main.py
```

```python
cd CA_Caesarean
streamlit run streamlit/dashboard.py
```
Make sure it writes the data in the bucket.

---
## Repository Structure
```
CA_Caesarean/
├── api/
│   ├── sources/
│   │   ├── __init__.py
│   │   ├── cms.py
│   │   ├── crosswalk.py
│   │   ├── hospital_scrapping.py
│   │   └── ingest_hcai.py
│   ├── Dockerfile
│   ├── main.py
│   ├── requirements.txt
│   ├── storage.py
│   └── transform.py
│
├── streamlit/
│   ├── services/
│   │   └── .gitkeep
│   ├── visualizations/
│   │   └── .gitkeep
│   ├── Dockerfile
│   ├── dashboard.py
│   └── requirements.txt
│
├── .env_template
├── .gitignore
├── README.md
└── gcloud_command.sh
```
