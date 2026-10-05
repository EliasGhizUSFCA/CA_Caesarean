"""Chloe's integration point: extend render_results with charts/maps here."""
import pandas as pd
import streamlit as st
from user_definition import METRICS

def render_results(records, metric, demo=False):
    frame = pd.DataFrame(records)
    a, b, c = st.columns(3)
    a.metric('Hospitals in results', frame['hospital_id'].nunique())
    b.metric('Reporting selected measure', int(frame[metric].notna().sum()))
    c.metric('Missing selected measure', int(frame[metric].isna().sum()))
    st.caption('Rates are shown as reported; missing data are not treated as zero. No hospital ranking or statewide average is calculated.')
    labels = {r['hospital_id']: f"{r['hospital_name']} · {r['county']} · {r['hospital_id']}" for r in records}
    selected = st.multiselect('Select hospitals to compare (optional)', options=list(labels), format_func=labels.get, max_selections=6, key='comparison')
    visible = frame[frame['hospital_id'].isin(selected)] if selected else frame
    st.subheader('Hospital comparison' if selected else 'Hospital results')
    st.caption('Select up to six hospitals above. Download contains the rows currently shown.')
    columns = ['hospital_name', 'county', 'ownership', 'year', metric, 'hospital_id']
    display = visible[columns].rename(columns={
        'hospital_name': 'Hospital', 'county': 'County', 'ownership': 'Ownership',
        'year': 'Year', 'hospital_id': 'Hospital ID', metric: METRICS[metric] + ' (%)',
    })
    st.dataframe(display, hide_index=True, use_container_width=True,
        column_config={METRICS[metric] + ' (%)': st.column_config.NumberColumn(format='%.1f%%'), 'Year': st.column_config.NumberColumn(format='%d')})
    export = visible.copy()
    export['data_mode'] = 'SYNTHETIC_DEMO' if demo else 'LIVE_API'
    for column in export.select_dtypes(include='object'):
        export[column] = export[column].map(lambda v: "'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@', '\t', '\r')) else v)
    st.download_button('Download displayed data (CSV)', export.to_csv(index=False).encode('utf-8'),
        file_name=('DEMO_' if demo else '') + 'ca_caesarean_hospitals.csv', mime='text/csv')
    # Add Chloe's visualizations here using `visible` and `metric`.
    # Keep primary C-section and NTSV separate; never convert missing rates to 0.
