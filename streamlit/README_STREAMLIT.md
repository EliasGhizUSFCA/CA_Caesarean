# Mamoune's Streamlit contribution

Built for the CA_Caesarean repository at commit `4e2fa26` on the local branch
`feature/streamlit-mamoune`. No remote branch, PR or deployment has been created.

## What is implemented

- Explore and About pages, county/year/ownership/measure controls.
- Form submission so editing filters does not repeatedly call the API.
- Server-side API client, request timeouts, validation, loading and error messages.
- Empty-data states, missing values, and stale-result clearing after failures.
- Optional selection of up to six hospitals and CSV export of displayed records.
- Explicit synthetic demo mode that runs without any backend or GCP account.
- A separate `results_view.py` function for Chloe to extend with charts/maps.

The actual backend endpoints were placeholders at the inspected commit. Live
integration is implemented against a proposed contract, and tested with a local
HTTP fixture, but has not been verified against the team's real data service.

## Run on your Mac

After extracting the ZIP, open a terminal in its `CA_Caesarean_Streamlit` folder.
The same commands work from the root of the team repository after copying in the
provided `streamlit` files:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r streamlit/requirements.txt
python -m streamlit run streamlit/dashboard.py
```

Open `http://localhost:8501` if your browser does not open automatically.
Leave **Demo data** selected, then click **Load hospitals**.
No configuration is required for demo mode. Stop the app with Control+C.

## Connect the real backend

1. Give `API_CONTRACT.md` to Narayan and Mary and agree the endpoint/field names.
2. Copy `streamlit/.env_template` to `streamlit/.env`.
3. Set `API_SERVICE_URL` to their running backend URL; set endpoint paths if needed.
4. Restart Streamlit, select **Live API**, and load hospitals.
5. Check a known hospital/year against the underlying dataset before presentation.

A local backend normally uses `http://localhost:8000`. Inside Docker, localhost
means that container, not the API container. The deployment team must supply a
reachable API URL. This package does not deploy services or modify cloud resources.

## Files and how they work

| File | Responsibility |
| --- | --- |
| `dashboard.py` | Navigation, form widgets, loading/error messages and session state |
| `api_client.py` | HTTP requests, proposed schema validation and safe error messages |
| `data_service.py` | Demo adapter and verification that results match requested filters |
| `user_definition.py` | Environment settings and measure labels |
| `results_view.py` | Basic comparison table and CSV; Chloe's chart integration point |
| `data/demo_hospitals.json` | Clearly fictional test records, including missing values |
| `.env_template` | Documented frontend configuration |
| `tests/` | UI, API failure and local HTTP integration checks |

When you click Load hospitals, the form submits all controls together. The data
source receives the year, county and ownership. Demo mode filters local JSON;
live mode calls the API. The selected measure chooses which returned rate to
show. A successful response is stored in session state so comparing hospitals
or downloading data does not send another API request. A failed load removes the
previous result. Switching sources removes old results and filter options.

For Chloe: extend `render_results(records, metric, demo=False)` in `results_view.py`.
`visible` already contains the selected hospitals and `metric` identifies the
chosen rate column. Maps require additional validated location fields; those
are deliberately not assumed in this initial contract.

For Elias: integrate the requirements/configuration into the team setup and
validate deployment. The API requirements and team Docker placeholders are not
included or changed by this frontend handoff.

## Add to your team's Git branch

First run `git status` in your existing team repository. Commit or stash unrelated
work before pulling; do not overwrite anyone else's updated Streamlit files.
The ZIP's `streamlit/` folder contains only this contribution. Review differences
against the current remote version before copying it into the repository.

If the branch does not exist yet, start from an up-to-date main:

```bash
git switch main
git pull --ff-only
git switch -c feature/streamlit-mamoune
```

If it already exists, use `git switch feature/streamlit-mamoune` instead.
After copying the files and running the app/tests:

```bash
git add streamlit
git diff --cached
git commit -m "Add Streamlit controls and API integration"
git push -u origin feature/streamlit-mamoune
```

Open a pull request from `feature/streamlit-mamoune` into `main` on GitHub, as the
assignment requires. Suggested description:

> Implements the hospital explorer page, year/county/ownership controls,
> hospital comparison selection, and a validated API client with loading,
> empty and error states. Includes a clearly labelled synthetic demo so the
> frontend can be reviewed before backend completion. Live endpoints follow
> API_CONTRACT.md and still need agreement and real-service integration checks.
> Charts are isolated in results_view.py for Chloe's contribution.

## Tests

From the repository/package root, using the virtual environment above:

```bash
python -m pip install -r streamlit/requirements-dev.txt
python -m pytest streamlit/tests -q
```

Manual presentation check: load default demo, filter San Francisco, compare one
hospital, switch to NTSV (one value is missing), try a county/ownership combination
with no results, download CSV, visit About, then test Live API with your backend.
The demo is not real data and is not a complete final project submission.

References used for implementation:
- https://docs.streamlit.io/develop/api-reference/execution-flow/st.form
- https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest
