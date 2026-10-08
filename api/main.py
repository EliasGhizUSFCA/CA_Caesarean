from fastapi import FastAPI, HTTPException
from sources import cms, ingest_hcai
from storage import save_dataframe, save_file

app = FastAPI()

@app.post("/cms-hospitals")
def run_cms_hospitals(state: str = "CA"):
    try:
        df = cms.fetch(state)
    except ValueError as e:
        raise HTTPException(404, str(e))
    path = save_dataframe(df, "cms-hospitals")
    return {"rows": len(df), "path": path}

@app.post("/hcai")
def run_hcai():
    data = ingest_hcai.fetch()
    path = save_file(data, "hcai", "data.xlsx")
    return {"bytes": len(data), "path": path}