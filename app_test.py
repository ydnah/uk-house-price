import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

import requests
import json

from uk_outcodes import uk_outcodes

@st.cache_data
def load_data(df_path):
    df = pd.read_csv(df_path)
    df['outcode'] = df['outcode'].str.replace(', UK', '')
    return df

df = load_data('out.csv')
unique_outcodes = list(uk_outcodes.keys())

def fetch_geojson(outcode):
    url = f"https://raw.githubusercontent.com/missinglink/uk-postcode-polygons/master/geojson/{outcode}.geojson"
    response = requests.get(url)
    return response.json()

def filter_df(df, year, outcode_prefix):
    filtered_df = df[(df['year'] == year) & (df['outcode'].str.startswith(outcode_prefix))]
    avg_price = filtered_df.groupby('outcode', as_index=False)['price'].mean()
    
    center_lat = filtered_df['Latitude'].mean()
    center_lon = filtered_df['Longitude'].mean()
    center_coords = {"lat": center_lat, "lon": center_lon}
    
    return avg_price, center_coords

def update_geojson(geojson, df):
    outcode_to_price = dict(zip(df['outcode'], df['price']))
    
    for feature in geojson["features"]:
        outcode = feature["properties"]["name"]  
        if outcode in outcode_to_price:
            feature["properties"]["average price"] = outcode_to_price[outcode]
        else:
            feature["properties"]["average price"] = None
            
def create_choropleth_mapbox(df, year, outcode):
    geojson = fetch_geojson(outcode)
    df_filtered, center_coords = filter_df(df, year, outcode)
    update_geojson(geojson, df_filtered)
    
    fig = px.choropleth_mapbox(df_filtered, geojson=geojson, color="price",
                           locations="outcode", featureidkey="properties.name",
                           center=center_coords, mapbox_style="carto-darkmatter", zoom=8.5)

    fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
    return fig

if 'response' not in st.session_state:
    st.session_state.response = {}

response = st.session_state.response

choropleth_form = st.form('choropleth_form')

selected_outcode = choropleth_form.selectbox("Select an outcode", unique_outcodes, key='outcode')
selected_year = choropleth_form.slider('Select year', 1995, 2023, 2023, key='year')
submit_button = choropleth_form.form_submit_button('Generate')
reset_button = choropleth_form.form_submit_button('Delete graphs')

graph_placeholder = st.empty()

if submit_button:
    response['first'] = (selected_year, selected_outcode)
    st.session_state.response = response

if reset_button:
    if 'response' in st.session_state:
        del st.session_state['response']
        st.rerun()

if 'first' in response:
    year1, outcode1 = response['first']
    fig1 = create_choropleth_mapbox(df, year1, outcode1)
    graph_placeholder.plotly_chart(fig1)
    
    #compare_form = st.form('compare_form')
    #selected_outcode_compare = compare_form.selectbox("Select an outcode to compare", unique_outcodes, key='compare_outcode')
    #selected_year_compare = compare_form.slider('Select year to compare', 1995, 2023, 2023, key='compare_year')
    compare_button = choropleth_form.form_submit_button('Compare')
    
    if compare_button:
        response['second'] = (selected_year, selected_outcode)
        st.session_state.response = response

if 'second' in response:
    year2, outcode2 = response['second']
    fig2 = create_choropleth_mapbox(df, year2, outcode2)
    
    if fig2:
        with graph_placeholder.container():
            st.plotly_chart(fig1)
            st.plotly_chart(fig2)
        


st.info('If you don\'t see the map change, scroll out', icon="ℹ️")



