import streamlit as st
import pandas as pd

st.title("Ceasarean Project Dashboard")
st.header("Visualization of Ceasrian Project Data")
st. write("This dashboard shows caeserean delivery rates differ between hospitals in California") 

county = st.sidebar.selectbox("Select a County", ("Los Angeles", "San Francisco", "San Diego", "Orange County", "Sacramento"), disabled=False)
st.write(f"You selected: {county}")

st.sidebar.header("Our Filters")
#side bar control for visualisaing the graph
select_box_graph = st.sidebar.selectbox("How would you like to visualize the data?", ("Bar Chart", "Line Chart", "Scatter Plot"), disabled=True)


st.subheader("Hospital map")
st.write( "need to connect to Hospital data")
st.subheader("Hospital comparison")

