# Proposed API contract — needs agreement from Narayan and Mary

At the inspected repository commit `4e2fa26`, `api/main.py` contained a placeholder,
not running endpoints. These paths and field names are proposals, not existing APIs.
The frontend uses server-side HTTP GET requests. It never downloads source data,
joins datasets, or accesses a GCP bucket itself.

## GET /filters

Return filter options from the actual joined dataset (not hard-coded options):

```json
{
  "years": [2024, 2023],
  "counties": ["Alameda", "San Francisco"],
  "ownership_types": ["Government", "Nonprofit", "For-profit"]
}
```

Empty arrays are valid; no years produces an empty-data screen.

## GET /hospitals

Query parameters: `year` (required integer), `county` (optional string),
`ownership` (optional string). Omitted optional parameters mean all values.
The client uses `requests.get(..., params=...)` to encode these safely.
Example: `/hospitals?year=2024&county=Alameda`.

Return a complete, filtered result in this shape:

```json
{
  "source": "Synthetic example only — replace with the actual sources",
  "updated_at": "2026-10-04T00:00:00Z",
  "records": [
    {
      "hospital_id": "DEMO-003",
      "hospital_name": "Demo Redwood Hospital",
      "county": "Alameda",
      "ownership": "Nonprofit",
      "year": 2024,
      "cesarean_rate": 25.8,
      "primary_cesarean_rate": 18.1,
      "ntsv_cesarean_rate": null,
      "vbac_rate": 17.1
    }
  ]
}
```

- One row per hospital/year after joining and pivoting procedure records.
- `hospital_id` is a stable string; preserve leading zeros. Do not join hospitals
  on name alone. Use the validated facility crosswalk in the backend.
- Required: ID, name, county, ownership (nonempty strings), year (integer).
  Represent unavailable ownership explicitly as `Unknown`.
- Rates are numeric percentages on a **0–100 scale**, not 0–1 fractions or strings.
  Each field must retain its own documented denominator and source definition.
- Missing/suppressed rates must be `null` (not 0, `-`, `NaN`, or a suppression code).
  An omitted rate field is treated as unavailable.
- Primary C-section is not interchangeable with NTSV. Do not populate NTSV from
  primary C-section or infer rates from honor-roll membership.
- No matches: HTTP 200 with `{"records": []}`. Metadata is optional but recommended.
- HTTP errors: use 401/403 for denied access, 422 for invalid parameters, and 5xx
  for server failures. Do not return stack traces, credentials, or internal paths.
- The current client expects the complete filtered response, without pagination.
  If pagination is introduced, update the client before connecting it; do not
  silently return only the first page.
- Unknown fields are ignored. Maps, county context, benchmarks and per-measure
  provenance can be added when those fields have a confirmed backend contract.

## Connection

Set `API_SERVICE_URL` in `streamlit/.env` to the real backend URL and choose Live
API in the sidebar. Paths are separately configurable with `API_FILTERS_PATH`
and `API_HOSPITALS_PATH`. Matching path names alone is insufficient: JSON fields
and query parameter names must also match. Adapt `api_client.py` if needed.

`API_TOKEN` supports an optional static bearer token. It does not implement GCP
service-account authentication or automatic Cloud Run identity-token refresh.
If the deployed API is IAM-protected, the deployment team must add that flow.
The frontend makes read-only calls; ingestion/refresh jobs belong to the API team.
