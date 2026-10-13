from fastapi import FastAPI, HTTPException
from sources import cms, ingest_hcai
from sources.hospital_scrapping import hospital_scrapping
from storage import save_dataframe, save_file
from datetime import date
from sources import crosswalk
import json
import pandas as pd
import io


app = FastAPI()

@app.post("/cms-hospitals")
def run_cms_hospitals(state: str = "CA"):
    try:
        df = cms.fetch(state)
    except ValueError as e:
        raise HTTPException(404, str(e))
    path = save_dataframe(df, "cms")
    return {"rows": len(df), "path": path}

@app.post("/hcai")
def run_hcai():
    data = ingest_hcai.fetch()

    df = pd.read_excel(
        io.BytesIO(data),
        dtype={"OSHPD_ID": str},
    )

    json_data = df.to_json(orient="records", indent=4)

    path = save_file(json_data, "hcai", "data.json")

    return {"rows": len(df), "path": path}

@app.post("/scrape-hospitals")
def run_scrape_hospitals():
    results = hospital_scrapping()

    path = save_file(
        json.dumps(results, indent=4),
        "scraped-hospitals",
        "data.json",
    )

    return {"hospitals": len(results), "path": path}

@app.post("/crosswalk")
def run_crosswalk():
    data = crosswalk.fetch()
    df = crosswalk.frame(data)

    json_data = df.to_json(orient="records", indent=4)

    path = save_file(
        json_data,
        "crosswalk",
        "data.json",
        partition=date.today().isoformat(),
    )

    return {"rows": len(df), "path": path}