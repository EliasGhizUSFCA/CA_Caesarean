"""Proposed API boundary. Adapt here when the team's contract is finalized."""
import math
from urllib.parse import urlparse
import requests
RATE_FIELDS = ('cesarean_rate', 'primary_cesarean_rate', 'ntsv_cesarean_rate', 'vbac_rate')

class APIError(Exception):
    """A safe, actionable message to display in the UI."""

def validate_filters(payload):
    if not isinstance(payload, dict):
        raise APIError('The filters response must be a JSON object. See API_CONTRACT.md.')
    for key in ('years', 'counties', 'ownership_types'):
        if not isinstance(payload.get(key), list):
            raise APIError(f'The filters response is missing the {key} list.')
    if any(type(y) is not int or not 1900 <= y <= 2100 for y in payload['years']):
        raise APIError('Filter years must be integer calendar years.')
    for key in ('counties', 'ownership_types'):
        if any(not isinstance(v, str) or not v.strip() for v in payload[key]):
            raise APIError(f'Every {key} value must be a nonempty string.')
    return {
        'years': sorted(set(payload['years']), reverse=True),
        'counties': sorted(set(payload['counties'])),
        'ownership_types': sorted(set(payload['ownership_types'])),
    }

def validate_response(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('records'), list):
        raise APIError('The API must return a JSON object with a records list. See API_CONTRACT.md.')
    clean, seen = [], set()
    for row in payload['records']:
        if not isinstance(row, dict):
            raise APIError('Every hospital record must be a JSON object.')
        row = dict(row)
        for key in ('hospital_id', 'hospital_name', 'county', 'ownership'):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise APIError(f'A hospital record has an invalid {key}. IDs must be strings.')
        if type(row.get('year')) is not int or not 1900 <= row['year'] <= 2100:
            raise APIError('A hospital record has an invalid year.')
        identity = (row['hospital_id'], row['year'])
        if identity in seen:
            raise APIError('Duplicate hospital/year records received. The backend must join them into one record.')
        seen.add(identity)
        for key in RATE_FIELDS:
            value = row.get(key)
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100):
                raise APIError(f'{key} must be a percentage from 0 to 100, or null for unavailable data.')
            row[key] = value
        clean.append({key: row[key] for key in ('hospital_id', 'hospital_name', 'county', 'ownership', 'year', *RATE_FIELDS)})
    metadata = {}
    for key in ('source', 'updated_at'):
        value = payload.get(key)
        if value is not None and not isinstance(value, str):
            raise APIError(f'The response {key} must be text or null.')
        metadata[key] = value
    return {'records': clean, **metadata}

class HospitalAPI:
    def __init__(self, base_url, filters_path='/filters', hospitals_path='/hospitals', token=''):
        parsed = urlparse(base_url)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.query or parsed.fragment or parsed.username:
            raise APIError('Set API_SERVICE_URL to a valid HTTP(S) server URL in .env.')
        for path in (filters_path, hospitals_path):
            if not path.startswith('/') or path.startswith('//') or '?' in path or '#' in path:
                raise APIError('API endpoint paths must start with a single slash and contain no query string.')
        self.base_url = base_url.rstrip('/')
        self.filters_path, self.hospitals_path = filters_path, hospitals_path
        self.headers = {'Accept': 'application/json'}
        if token:
            self.headers['Authorization'] = f'Bearer {token}'

    def _get(self, path, params=None):
        try:
            response = requests.get(self.base_url + path, params=params, headers=self.headers, timeout=(5, 25), allow_redirects=False)
            if response.status_code in (401, 403):
                raise APIError('The API denied access. Check backend permissions and API_TOKEN.')
            if response.status_code == 404:
                raise APIError('This API endpoint does not exist yet. Ask the API team to implement the proposed contract or update the endpoint path.')
            if response.status_code == 422:
                raise APIError('The API rejected these filters. Check the parameter names and values against the backend contract.')
            if response.status_code == 429:
                raise APIError('The API is busy or rate-limited. Please try again shortly.')
            if 300 <= response.status_code < 400:
                raise APIError('The API redirected the request. Configure the final endpoint URL directly.')
            response.raise_for_status()
            try:
                return response.json()
            except ValueError as exc:
                raise APIError('The API returned invalid JSON. Ask the API team to check this endpoint.') from exc
        except requests.Timeout as exc:
            raise APIError('The API took too long to respond. Try again or ask the API team to check the service.') from exc
        except requests.ConnectionError as exc:
            raise APIError('Cannot reach the API. Check that the backend is running and API_SERVICE_URL is correct.') from exc
        except requests.RequestException as exc:
            raise APIError('The API request failed. Check the backend logs and try again.') from exc

    def filters(self):
        return validate_filters(self._get(self.filters_path))

    def hospitals(self, year, county=None, ownership=None):
        params = {'year': year}
        if county:
            params['county'] = county
        if ownership:
            params['ownership'] = ownership
        return validate_response(self._get(self.hospitals_path, params))
