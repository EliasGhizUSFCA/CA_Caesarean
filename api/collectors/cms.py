import requests


def fetch_hospitals(state: str = "CA") -> dict:
    """Fetch all pages of hospital records from CMS for a state."""
    url = "https://data.cms.gov/provider-data/api/1/datastore/query/xubh-q36u/0"

    params = {
        "conditions[0][property]": "state",
        "conditions[0][value]": state,
        "conditions[0][operator]": "=",
        "limit": 100,
        "offset": 0,
    }

    all_hospitals = []

    while True:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()

        if not isinstance(payload, dict):
            raise ValueError("CMS returned an unexpected response.")

        hospitals = payload.get("results")
        total = payload.get("count")

        if not isinstance(hospitals, list):
            raise ValueError("CMS response is missing hospital records.")

        if not isinstance(total, int) or total < 0:
            raise ValueError("CMS returned an invalid record count.")

        all_hospitals.extend(hospitals)

        if len(all_hospitals) >= total:
            break

        if not hospitals:
            raise ValueError("CMS returned an empty page before completion.")

        params["offset"] += len(hospitals)

    return {
        "hospitals": all_hospitals,
        "total_available": total,
    }