import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import Mock
import pytest
import requests
from streamlit.testing.v1 import AppTest
from api_client import APIError, HospitalAPI, validate_response
from data_service import DemoSource, check_requested_filters

APP = str(Path(__file__).resolve().parents[1] / 'dashboard.py')

def start():
    app = AppTest.from_file(APP).run()
    assert not app.exception
    return app

def submit(app):
    next(b for b in app.button if b.label == 'Load hospitals').click().run()
    assert not app.exception
    return app

def test_demo_filters_comparison_and_missing_values():
    app = start()
    app.selectbox(key='county').select('San Francisco')
    app.selectbox(key='measure').select('ntsv_cesarean_rate')
    submit(app)
    assert len(app.dataframe[0].value) == 2
    assert app.dataframe[0].value['NTSV C-section rate (%)'].isna().sum() == 1
    app.multiselect(key='comparison').set_value(['DEMO-001']).run()
    assert not app.exception
    assert len(app.dataframe[0].value) == 1
    # New query resets an old hospital selection.
    app.selectbox(key='county').select('Alameda')
    submit(app)
    assert app.multiselect(key='comparison').value == []
    assert set(app.dataframe[0].value['County']) == {'Alameda'}

def test_empty_results_and_about():
    app = start()
    app.selectbox(key='county').select('San Francisco')
    app.selectbox(key='ownership').select('For-profit')
    submit(app)
    assert any('No hospitals match' in item.value for item in app.info)
    assert len(app.dataframe) == 0
    app.sidebar.radio[0].set_value('About the project').run()
    assert not app.exception
    assert any(x.value == 'The project' for x in app.subheader)

def test_live_failure_does_not_show_demo_results(monkeypatch):
    app = submit(start())
    assert len(app.dataframe) == 1
    def fail(*args, **kwargs):
        raise requests.ConnectionError()
    monkeypatch.setattr(requests, 'get', fail)
    app.sidebar.radio[1].set_value('Live API').run()
    assert not app.exception
    assert any('Cannot reach' in x.value for x in app.error)
    assert len(app.dataframe) == 0
    app.sidebar.radio[1].set_value('Demo data').run()
    submit(app)
    assert len(app.dataframe[0].value) == 8

def test_live_success_then_failure_clears_stale_results(monkeypatch):
    demo = DemoSource()
    monkeypatch.setattr(HospitalAPI, 'filters', lambda self: demo.filters())
    monkeypatch.setattr(HospitalAPI, 'hospitals', lambda self, y, c, o: demo.hospitals(y,c,o))
    app = start()
    app.sidebar.radio[1].set_value('Live API').run()
    submit(app)
    assert len(app.dataframe[0].value) == 8
    def fail(*args, **kwargs):
        raise APIError('Simulated backend failure')
    monkeypatch.setattr(HospitalAPI, 'hospitals', fail)
    submit(app)
    assert len(app.dataframe) == 0
    assert app.error[0].value == 'Simulated backend failure'

@pytest.mark.parametrize('status', [401,403,404,422,429,500,302])
def test_http_failures_are_safe(monkeypatch, status):
    response = requests.Response()
    response.status_code = status
    response._content = b'sensitive backend details'
    monkeypatch.setattr(requests, 'get', lambda *a, **k: response)
    with pytest.raises(APIError) as error:
        HospitalAPI('http://localhost:8000').filters()
    assert 'sensitive' not in str(error.value)

@pytest.mark.parametrize('exception', [requests.Timeout(), requests.ConnectionError()])
def test_network_failures(monkeypatch, exception):
    monkeypatch.setattr(requests, 'get', Mock(side_effect=exception))
    with pytest.raises(APIError):
        HospitalAPI('http://localhost:8000').filters()

def test_invalid_json(monkeypatch):
    response = requests.Response(); response.status_code = 200; response._content = b'not json'
    monkeypatch.setattr(requests, 'get', lambda *a, **k: response)
    with pytest.raises(APIError, match='invalid JSON'):
        HospitalAPI('http://localhost:8000').filters()

@pytest.mark.parametrize('value', [-1, 101, '25%', float('nan'), True])
def test_invalid_rates_rejected(value):
    payload = DemoSource().hospitals(2024)
    payload['records'][0]['cesarean_rate'] = value
    with pytest.raises(APIError):
        validate_response(payload)

def test_duplicates_and_ignored_filters_rejected():
    payload = DemoSource().hospitals(2024)
    with pytest.raises(APIError, match='outside'):
        check_requested_filters(payload, 2024, 'Alameda', None)
    payload['records'].append(dict(payload['records'][0]))
    with pytest.raises(APIError, match='Duplicate'):
        validate_response(payload)

def test_actual_http_roundtrip():
    demo = DemoSource()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlparse(self.path)
            if path.path == '/filters':
                payload = demo.filters()
            else:
                query = parse_qs(path.query)
                payload = demo.hospitals(int(query['year'][0]), query.get('county',[None])[0], query.get('ownership',[None])[0])
            body = json.dumps(payload).encode()
            self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers(); self.wfile.write(body)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        client = HospitalAPI(f'http://127.0.0.1:{server.server_port}')
        assert client.filters()['years'] == [2024,2023,2022]
        result = client.hospitals(2024, 'San Francisco', 'Nonprofit')
        assert len(result['records']) == 1
        assert result['records'][0]['hospital_id'] == 'DEMO-001'
    finally:
        server.shutdown(); server.server_close(); thread.join()
