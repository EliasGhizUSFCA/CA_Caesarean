"""Crosswalk + join layer. WIP."""
import io
import requests
import pandas as pd

#check if needed
CKAN= "https://data.chhs.ca.gov/api/3/action"
PACKAGE_ID= "licensed-facility-crosswalk"
RESOURCE_NAME= "ELMS-ASPEN-OSHPD"

def fetch() -> bytes:
    r=requests.get(f"{CKAN}/package_show",params={"id": PACKAGE_ID},timeout=60)
    r.raise_for_status()
    resources=r.json()["result"]["resources"]
    res=next(x for x in resources if "ELMS-ASPEN-OSHPD" in x["name"])
    f=requests.get(res["url"],timeout=120)
    f.raise_for_status()
    return f.content
