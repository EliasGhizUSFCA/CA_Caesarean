"""Mamoune's Streamlit page, input controls, and API integration."""
import streamlit as st
from api_client import APIError, HospitalAPI
from data_service import DemoSource, check_requested_filters
from results_view import render_results
from user_definition import API_SERVICE_URL, API_TOKEN, DEFAULT_MODE, FILTERS_PATH, HOSPITALS_PATH, METRICS

st.set_page_config(page_title='CA Caesarean | Hospital explorer', page_icon='🏥', layout='wide')
with st.sidebar:
    st.title('CA Caesarean')
    st.caption('California hospital explorer')
    page = st.radio('Navigation', ['Explore hospitals', 'About the project'])
    mode = st.radio('Data source', ['Demo data', 'Live API'], index=1 if DEFAULT_MODE == 'live' else 0)
    st.caption('Demo mode uses fictional hospitals and synthetic rates. Live mode requires the team’s API.')
st.title('Explore maternity procedure rates')
st.write('Choose a year and location, then compare the available hospital measures.')
demo = mode == 'Demo data'
if demo:
    st.warning('DEMO ONLY — all hospital names and rates below are synthetic. They are for interface testing, not hospital selection.')
else:
    st.info('Live API mode — results are loaded from the configured team backend.')
if page == 'About the project':
    st.subheader('The project')
    st.write('CA Caesarean explores variation in California hospital procedure rates. The team plans to combine HCAI procedure data, CMS hospital characteristics, Census county data, and maternity quality information.')
    st.subheader('How to use this interface')
    st.markdown('1. Choose a data source.\n2. Set year, county, ownership and measure.\n3. Click **Load hospitals**.\n4. Select hospitals to compare and download the displayed rows.')
    st.subheader('Reading the results')
    st.write('Primary C-section and NTSV C-section are different measures and are kept separate. Missing or suppressed values appear as missing, never as zero. Interpret each measure using the source’s definition and denominator. Hospital-level rates alone do not establish quality or explain individual outcomes.')
    st.subheader('Team responsibilities')
    st.write('Mamoune: page structure, controls and API client. Chloe: charts and results presentation. Elias: interface integration and validation. Narayan and Mary: API and data services.')
    st.caption('This is an educational data exploration project, not individual medical advice.')
    st.stop()

source_key = (mode, API_SERVICE_URL, FILTERS_PATH, HOSPITALS_PATH)
if st.session_state.get('source_key') != source_key:
    for key in ('filter_options', 'result', 'loaded_query', 'comparison', 'year', 'county', 'ownership', 'measure'):
        st.session_state.pop(key, None)
    st.session_state['source_key'] = source_key
try:
    source = DemoSource() if demo else HospitalAPI(API_SERVICE_URL, FILTERS_PATH, HOSPITALS_PATH, API_TOKEN)
    if st.sidebar.button('Refresh filter options'):
        for key in ('filter_options', 'result', 'loaded_query', 'comparison', 'year', 'county', 'ownership'):
            st.session_state.pop(key, None)
    if 'filter_options' not in st.session_state:
        with st.spinner('Loading available filters…'):
            st.session_state['filter_options'] = source.filters()
    options = st.session_state['filter_options']
except APIError as exc:
    st.error(str(exc))
    st.caption('Use “Refresh filter options” to retry, or select Demo data to explore the interface.')
    st.stop()
if not options['years']:
    st.info('No reporting years are available yet. Refresh after the backend loads data.')
    st.stop()
with st.form('hospital_filters'):
    st.subheader('Find hospitals')
    a, b, c, d = st.columns(4)
    year = a.selectbox('Reporting year', options['years'], key='year')
    county = b.selectbox('County', [None, *options['counties']], format_func=lambda v: v or 'All counties', key='county')
    ownership = c.selectbox('Ownership', [None, *options['ownership_types']], format_func=lambda v: v or 'All ownership types', key='ownership')
    metric = d.selectbox('Measure', list(METRICS), format_func=METRICS.get, key='measure')
    submitted = st.form_submit_button('Load hospitals', type='primary')
if submitted:
    for key in ('result', 'loaded_query', 'comparison'):
        st.session_state.pop(key, None)
    try:
        with st.spinner('Loading hospital results…'):
            result = check_requested_filters(source.hospitals(year, county, ownership), year, county, ownership)
        st.session_state['result'] = result
        st.session_state['loaded_query'] = (year, county, ownership, metric)
    except APIError as exc:
        st.error(str(exc))
if 'result' not in st.session_state:
    st.info('Choose your filters and click Load hospitals to begin.')
    st.stop()
result = st.session_state['result']
loaded_year, loaded_county, loaded_ownership, loaded_metric = st.session_state['loaded_query']
st.caption(f"Loaded selection: {loaded_year} · {loaded_county or 'All counties'} · {loaded_ownership or 'All ownership types'} · {METRICS[loaded_metric]}. Submit the form to apply new filters.")
if not result['records']:
    st.info('No hospitals match this selection. Try all counties or all ownership types.')
else:
    render_results(result['records'], loaded_metric, demo=demo)
st.caption('Source: ' + (result.get('source') or 'Not provided by API'))
st.caption('Data last updated: ' + (result.get('updated_at') or 'Not provided by API'))
