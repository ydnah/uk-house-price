from SPARQLWrapper import SPARQLWrapper, CSV
import pandas as pd
import io
import streamlit as st
import requests
import plotly.express as px
from geopy.geocoders import Nominatim
from datetime import datetime

# Define the SPARQL query function
def get_query_with_town(town_name, start_date, end_date):
    query_template = """
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
    PREFIX sr: <http://data.ordnancesurvey.co.uk/ontology/spatialrelations/>
    PREFIX ukhpi: <http://landregistry.data.gov.uk/def/ukhpi/>
    PREFIX lrppi: <http://landregistry.data.gov.uk/def/ppi/>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    PREFIX lrcommon: <http://landregistry.data.gov.uk/def/common/>

    SELECT ?town ?postcode ?amount ?date 
    WHERE
    {{
      ?addr lrcommon:town ?town ;
            lrcommon:postcode ?postcode.

      FILTER(?town = "{town_name}"^^xsd:string)

      ?transx lrppi:propertyAddress ?addr ;
              lrppi:pricePaid ?amount ;
              lrppi:transactionDate ?date .

      FILTER(?date >= "{start_date}"^^xsd:date && ?date <= "{end_date}"^^xsd:date)
    }}
    ORDER BY ?postcode
    """
    return query_template.format(town_name=town_name, start_date=start_date, end_date=end_date)

@st.cache_data
def return_data():
  # Set up the SPARQL endpoint URL and wrapper
  sparql_endpoint_url = "https://landregistry.data.gov.uk/landregistry/query"
  sparql = SPARQLWrapper(sparql_endpoint_url)
  
  # Create query and set the reutrn format
  query = get_query_with_town(town.upper(), start_date, end_date)
  sparql.setQuery(query)
  sparql.setReturnFormat(CSV)
  # Execute the query and get the results
  results = sparql.query().convert()
  # Read the results into a pandas DataFrame
  df = pd.read_csv(io.StringIO(results.decode("utf-8")))
  return df

def extract_outcode(postcode):
  for i, char in enumerate(postcode):
    if char.isdigit():
      return postcode[:i]
  return postcode

@st.cache_data
def modify_data(df):
  df['postcode'] = df['postcode'].str.split(' ').str[0]
  outcode = df['postcode'].iloc[0]
  outcode = extract_outcode(outcode)
  df = df.groupby('postcode', as_index=False)['amount'].mean()
  return df, outcode

@st.cache_data
def fetch_geojson(outcode):
  url = f"https://raw.githubusercontent.com/missinglink/uk-postcode-polygons/master/geojson/{outcode}.geojson"
  response = requests.get(url)
  return response.json()

def get_coords(town):
  geolocator = Nominatim(user_agent="my_map")
  location = geolocator.geocode(town + ", UK")
  if location:
    return (location.latitude, location.longitude)
  else:
    return None

def create_choropleth_mapbox():
  df = return_data()
  mod_df, outcode = modify_data(df)
  geojson = fetch_geojson(outcode)
  lat, lon = get_coords(town)
    
  fig = px.choropleth_mapbox(mod_df, geojson=geojson, color="amount",
                            locations="postcode", featureidkey="properties.name",
                            center={"lat": lat, "lon": lon},
                            mapbox_style="carto-darkmatter", zoom=9)

  fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
  return fig

# Streamlit app
st.title("UK House Price Data")

min_value = datetime(1995, 1, 1)
max_value = datetime.now()

data_form = st.form('data')
town = data_form.text_input("Town", "Wolverhampton")
start_date = data_form.date_input("Select start date", min_value=min_value, max_value=max_value, key='start_date')
end_date = data_form.date_input("Select start date", min_value=min_value, max_value=max_value, key='end_date')
submit_button = data_form.form_submit_button('Generate')

if submit_button:
  # clear the cache 
  return_data.clear()
  modify_data.clear()
  fetch_geojson.clear()
  
  fig = create_choropleth_mapbox()
  
  st.plotly_chart(fig)
  
