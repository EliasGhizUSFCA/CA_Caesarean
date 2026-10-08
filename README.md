# CA_Caesarean
C-section rates vary greatly from one California hospital to the next. Our team is exploring what drives that variation and building a dashboard to help the public understand these rates. By combining HCAI procedure rates with CMS hospital charactristics, Census county data, and CMQCC quality benchmarks, we created an interactive tool to help new families compare hospitals and decide where to deliver their babies.

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
Cesarean delivery is typically framed as a clinical decision made for an individual patient. However, c-section rates in the United States vary wildly across hospitals, even among fairly low risk births. Our project would seek to quantify that gap for hospitals in California with visualizations that utilize available observed hospital data. We will combine HCAI's utilization rates with CMS facility characteristics, scraped CMQCC and Cal Hospital Compare maternity measures, United States Census county data and finally the CalHHS facility crosswalk to join these datasets. The final product would be a maps and comparison view where a user could select a county and see available hospital's, c-section, NTSV c-section and VBAC rates side by side, filtered by year and hospital ownership type. This deliverable could serve expectant parents choosing a hospital for delivery and quality committees who want a more local benchmark than just the statewide average.

---

## Data Sources and Integration Goal
- Follow the direction given in the 1st assignment

### Sources
| # | Source & Link | Method | What it contains | Update frequency | Access requirements |
| --- | --- | --- | --- | --- | --- |
| 1 | [HCAI Utilization Rates for Selected Medical Procedures in California Hospitals](https://data.chhs.ca.gov/dataset/utilization-rates-for-selected-medical-procedures-in-california-hospitals) | File | About 3,300 rows, one per hospital per year per procedure: year, county, hospital, OSHPD_ID, procedure, count, rate per 100 deliveries, and latitude/longitude. We keep Cesarean, Primary Cesarean, and VBAC. Covers YEAR–YEAR, all California licnsed hospitals. | Annually last updated 10/10/2025 | None|
| 2 | [CMS Hospital General Information](https://data.cms.gov/provider-data/dataset/xubh-q36u) | API | About 5,400 rows, one per Medicare registered hospital in the U.S. but we will filter for CA. We use CCN, name, address, ZIP, county, hospital type, ownership, emergency services, birthing friendly designation, and overall star rating. | Quarterly | None; no published rate limit |
| 3 | [CalHHS Facility Crosswalk](https://data.chhs.ca.gov/dataset/licensed-facility-crosswalk) | CSV, grabbed at runtime | Connects HCAI_ID to CCN and NPI. Filter to hospitals only (General Acute Care Hospital 434, Acute Psychiatric Hospital 125, Chemical Dependency Recovery Hospital 10, Alternative Birthing Center 8); drop closed facilities using license/ASPEN status; determine a rule for parent/child facilities that share a CCN. | NA | None |
| 4 | [Cal Hospital Compare](https://calhospitalcompare.org/wp-content/provider_list.txt) | Scraping | Quality measures not covered by HCAI, scraped only for hospitals HCAI flags as delivering. Joins on OSHPD_ID (used in each URL). We use NTSV c-section rate, VBAC rate and availability, CNM delivery rate, episiotomy rate, exclusive human milk feeding, and Baby Friendly status. Values are strings that need stripping and casting; missing maternity data is expected for non-delivering hospitals, and all-zero rows for delivering hospitals get flagged for review. | NA | None |



Note: If we need a key, say which environment variable holds it and make sure that variable also appears in the .env_template

### Integration Goal
- Follow the direction given in the 1st assignment

---

## Setup Instructions (Locally)
NEED TO DO AT END==================

### Prerequisites
- Python 3.11+
- Docker
- A GCP service account key with access to `PROJECT_ID` / `BUCKET_NAME` / `DATASET_NAME`
- Census API key ([sign up here](https://api.census.gov/data/key_signup.html)), stored in `CENSUS_API_KEY`

### 1. Clone the repository
```bash
git clone https://github.com/EliasGhizUSFCA/CA_Caesarean.git
cd REPO
```

### 2. Configure environment variables
Copy the example file and fill in your own values:

```bash
cp .env_template .env
```

| Variable | Description | Example |
| --- | --- | --- |
| `GCP_SERVICE_ACCOUNT_KEY` | Absolute path to your service account JSON | `/Users/you/.ssh/key.json` |
| `SOURCE_API_KEY` | Key for SOURCE NAME (free tier) | `abc123...` |
| `API_SERVICE_URL` | Where the web app reaches the API | `http://api-server:8000` |

### 4. How to call your endpoint
To start the API server,
```python
fastapi run mycode.py
```

```python
requests.post("http://localhost:8000/something", json=something)
```
Make sure it writes the data in the bucket.

---
## Repository Structure
```
  API
  ├── Dockerfile
  ├── main.py
  ├── requirements.txt
  ├── storage.py
  ├── transform.py
  ├── data1.py
  ├── data2.py
  ├── data3.py
  └── data4.py

  Streamlit
  ├── Dockerfile
  ├── dashboard.py
  ├── requirements.txt
  └──  user_definition.py

├── .env_template
├── gcloud_command.sh
└── README.md
```
