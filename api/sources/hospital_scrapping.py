
import requests
from bs4 import BeautifulSoup
import json
import re
import time

listUrl = "https://calhospitalcompare.org/wp-content/provider_list.txt"
pageUrl = "https://calhospitalcompare.org/hospital/?id="
limit = 25

wanted = {
    "cesarean birth rate": "ntsv_cesarean_pct",
    "vbac rate": "vbac_pct",
    "vbac routinely available": "vbac_routinely_available",
    "deliveries by certified nurse midwives": "cnm_delivery_pct"
}


def cleanValue(value):
    value = value.replace("(lower is better)", "").strip()

    if value == "" or value.upper() == "NA":
        return None

    if value.lower() == "yes":
        return True

    if value.lower() == "no":
        return False

    try:
        return float(value.rstrip("%"))
    except ValueError:
        return value


def scrapeHospital(hospitalId):
    url = pageUrl + hospitalId
    response = requests.get(url, timeout=30)
    soup = BeautifulSoup(response.text, "html.parser")

    name = None
    heading = soup.find("h2")

    if heading:
        name = heading.get_text(strip=True)

    hospital = {
        "oshpd_id": hospitalId,
        "hospital_name": name,
        "ntsv_cesarean_pct": None,
        "vbac_pct": None,
        "vbac_routinely_available": None,
        "cnm_delivery_pct": None,
        "has_maternity_section": False
    }

    rows = soup.find_all("tr")

    for row in rows:
        cells = row.find_all(["th", "td"])

        if len(cells) < 2:
            continue

        label = cells[0].get_text(" ", strip=True)
        label = label.rstrip("?").lower()

        if label in wanted:
            column = wanted[label]
            value = cells[1].get_text(" ", strip=True)

            hospital[column] = cleanValue(value)
            hospital["has_maternity_section"] = True

            image = cells[1].find("img")

            if image:
                imageUrl = image.get("src", "")
                newColumn = column.replace("_pct", "") + "_insufficient_data"

                if "rating_images/7.png" in imageUrl:
                    hospital[newColumn] = True
                else:
                    hospital[newColumn] = False

    return hospital

def hospital_scrapping():

    response = requests.get(listUrl, timeout=30)
    hospitalIds = re.findall(r"id=(\d+)", response.text)

    uniqueIds = []

    for hospitalId in hospitalIds:
        if hospitalId not in uniqueIds:
            uniqueIds.append(hospitalId)

        if len(uniqueIds) == limit:
            break

    results = []

    for hospitalId in uniqueIds:
        try:
            hospitalData = scrapeHospital(hospitalId)
            results.append(hospitalData)
        except Exception as error:
            results.append({
            "oshpd_id": hospitalId,
            "error": str(error)
        })

    time.sleep(1)
    
    return results
