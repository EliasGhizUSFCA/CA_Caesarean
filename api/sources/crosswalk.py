"""Crosswalk + join layer. WIP."""
import io
import requests
import pandas as pd

CKAN= "https://data.chhs.ca.gov/api/3/action"
PACKAGE_ID= "licensed-facility-crosswalk"
RESOURCE_NAME= "ELMS-ASPEN-OSHPD"

HCAI_RESOURCE = "06f75573-e5b3-4ab3-a7a7-84ab56e83965"

#download current corsswalk workbook
def fetch() -> bytes:
    #filename changes, resolve it from CKAN
    r=requests.get(f"{CKAN}/package_show",params={"id": PACKAGE_ID},timeout=60)
    r.raise_for_status()
    resources=r.json()["result"]["resources"]
    #pcik the 1:1:1 crosswalk 
    res=next(x for x in resources if RESOURCE_NAME in x["name"])

    f=requests.get(res["url"],timeout=120)
    f.raise_for_status()
    return f.content

#parse the workbook
def frame(data: bytes) -> pd.DataFrame:
    df = pd.read_excel(io.BytesIO(data), dtype=str)
    df.columns = [c.strip().upper() for c in df.columns]
    return df

#reduce to only hosptials that are relevant
def hospitals_only(df: pd.DataFrame) -> pd.DataFrame:
    #only acute care
    df = df[df["FAC_FDR"]=="GENERAL ACUTE CARE HOSPITAL"] 

    #remove excluded, for organ transplant locations and such
    df = df[df["HCAI_ID"] != "EXCLUDED"]

    # get only locations with ccn number, needed to connect to cms
    has_ccn = df["CCN"].notna() & (df["CCN"].str.strip() != "")
    df =df[has_ccn].copy()

    #clean HCAI and CNN
    #cnn begins with 05 in CA, pad with zeros to protect join
    df["CCN"] = df["CCN"].str.strip().str.zfill(6)
    df["HCAI_ID"] = df["HCAI_ID"].str.strip()

    return df[["HCAI_ID", "CCN", "NPI", "FACNAME"]]


def fetch_hcai()-> pd.DataFrame:
    r=requests.get(f"{CKAN}/datastore_search_sql",params={"sql": f'SELECT * FROM "{HCAI_RESOURCE}"'},timeout=120)
    r.raise_for_status()
    df=pd.DataFrame(r.json()["result"]["records"], dtype=str)

    #oshpd id for statewide rows is "None" so missed by drop na
    df=df[df["OSHPD_ID"] != "None"]

    return df

#join tables
def build_join(hcai,xmap,cms_df,ccn_col="Facility ID"):

    #pad cms cols
    cms_df=cms_df.copy()
    cms_df[ccn_col]=cms_df[ccn_col].astype(str).str.strip().str.zfill(6)
    
    #left join hcai on HCAI and OSHPD ID
    step_1=hcai.merge(xmap, left_on="OSHPD_ID", right_on="HCAI_ID", how="left")

    #left join CMS on CCN
    step_2=step_1.merge(cms_df, left_on="CCN", right_on=ccn_col,how="left", indicator=True)

    return step_2
    