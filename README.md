# ADD YOUR PROJECT TITLE
Add a brief description of your project, in a sentence or two.

## Team Members

| Name | GitHubID | Role / Focus |
| --- | --- | --- |
| Chloe Buhl | cjbuhl | GCP,Docker, and Streamlit|
| Mary Kim | MaryHCDS | FastAPI and Report |
| Elias Ghiz | EliasGhizUSFCA | README and Streamlit |
| Narayan Poudel | naryan | FastAPI |
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
| 1 | [NAME](https://exact-url) | API | rows, columns, time range, geography — in your own words | daily / monthly / static | free key, 100 req/day |
| 2 | [NAME](https://exact-url) | File | ... | ... | none |
| 3 | [NAME](https://exact-url) | Scraped | ... | ... | `robots.txt` checked DATE |

Note: If we need a key, say which environment variable holds it and make sure that variable also appears in the .env_template

### Integration Goal
- Follow the direction given in the 1st assignment

---

## Setup Instructions (Locally)

### Prerequisites
- Python 3.11+
- A GCP service account key with access to PROJECT/BUCKET/DATASET
- Any source API keys listed in the table below

### 1. Clone the repository
```bash
git clone https://github.com/ORG/REPO.git
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
.
├── your_code.py
├── .env_template
└── README.md
```
