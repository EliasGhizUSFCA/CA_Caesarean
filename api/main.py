from fastapi import FastAPI, HTTPException

from api.collectors.cms import fetch_hospitals

app = FastAPI()

@app.get("/preview/cms")
def preview_hospitals():
    """Fetch a preview of hospital records from CMS for California."""
    try:
        result = fetch_hospitals(state="CA")
    except requests.exceptions.Timeout as exc:
        raise HTTPException(
            status_code=504,
            detail="CMS took too long to respond.",
        ) from exc
    except (requests.exceptions.RequestException, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Could not retrieve valid hospital data from CMS.",
        ) from exc

    return {
        "source": "CMS",
        "returned_count": len(result["hospitals"]),
        "total_available": result["total_available"],
        "hospitals": result["hospitals"],
    }