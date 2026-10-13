import os 
import requests 


def fetch():
    hcai_url = os.getenv("HCAI_DATA_URL")

    #download 
    response = requests.get(hcai_url)
    response.raise_for_status()

    return response.content