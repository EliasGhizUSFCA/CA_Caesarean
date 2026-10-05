"""Demo and live sources expose the same interface to the page."""
import json
from pathlib import Path
from api_client import APIError, validate_filters, validate_response

class DemoSource:
    def __init__(self):
        self.payload = validate_response(json.loads((Path(__file__).parent / 'data' / 'demo_hospitals.json').read_text()))

    def filters(self):
        rows = self.payload['records']
        return validate_filters({
            'years': list({r['year'] for r in rows}),
            'counties': list({r['county'] for r in rows}),
            'ownership_types': list({r['ownership'] for r in rows}),
        })

    def hospitals(self, year, county=None, ownership=None):
        return {**self.payload, 'records': [r for r in self.payload['records'] if
            r['year'] == year and (not county or r['county'] == county) and
            (not ownership or r['ownership'] == ownership)]}

def check_requested_filters(payload, year, county, ownership):
    """Reject unfiltered responses rather than mislabel them."""
    if any(r['year'] != year or (county and r['county'] != county) or
           (ownership and r['ownership'] != ownership) for r in payload['records']):
        raise APIError('The API returned records outside the requested filters. Ask the API team to check filtering.')
    return payload
