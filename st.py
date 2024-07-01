import io
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from geopy.geocoders import Nominatim
from SPARQLWrapper import CSV, SPARQLWrapper


# Define the query
def query(town_name, current_date):
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

    SELECT ?postcode ?amount ?date ?propertyTypeLabel
    WHERE
    {{
        ?addr lrcommon:town ?town ;
              lrcommon:postcode ?postcode.
        
        FILTER(?town = "{town_name}"^^xsd:string)
        
        ?transx lrppi:propertyAddress ?addr ;
                lrppi:pricePaid ?amount ;
                lrppi:transactionDate ?date ;
                lrppi:propertyType ?propertyType.
        
        OPTIONAL {{ ?propertyType rdfs:label ?propertyTypeLabel }}

        FILTER(?date >= "2000-01-01"^^xsd:date && ?date <= "{current_date}"^^xsd:date)
    }}
    """
    return query_template.format(town_name=town_name, current_date=current_date)


# Get data from sparql endpoint
@st.cache_data
def return_data(query):
    try:
        sparql_endpoint_url = "https://landregistry.data.gov.uk/landregistry/query"
        sparql = SPARQLWrapper(sparql_endpoint_url)
        sparql.setQuery(query)
        sparql.setReturnFormat(CSV)

        results = sparql.query().convert()
        df = pd.read_csv(io.StringIO(results.decode("utf-8")))

        if df.empty:
            raise ValueError("No data found for the selected town and date range.")

        return df

    except Exception as e:
        st.error("An error occurred while fetching data: " + str(e))
        return None


# Get outcode for geodata seach
def extract_outcode(postcode):
    for i, char in enumerate(postcode):
        if char.isdigit():
            return postcode[:i]
    return postcode


# Fetch geojson data
@st.cache_data
def fetch_geojson(outcode):
    url = f"https://raw.githubusercontent.com/missinglink/uk-postcode-polygons/master/geojson/{outcode}.geojson"
    response = requests.get(url)
    return response.json()


# Get coordinates for choropleth
def get_coords(town):
    geolocator = Nominatim(user_agent="my_map")
    location = geolocator.geocode(town + ", UK")
    if location:
        return (location.latitude, location.longitude)
    else:
        return None


# Create choropleth map
def create_choropleth_mapbox(df, year, town):
    include = df[df["date"].dt.year == year]
    include["postcode"] = include["postcode"].str.split(" ").str[0]
    postcode = df["postcode"].iloc[0]
    outcode = extract_outcode(postcode)
    include = include.groupby("postcode", as_index=False)["amount"].mean()

    geojson = fetch_geojson(outcode)
    lat, lon = get_coords(town)

    fig = px.choropleth_mapbox(
        include,
        geojson=geojson,
        color="amount",
        opacity=0.6,
        locations="postcode",
        featureidkey="properties.name",
        center={"lat": lat, "lon": lon},
        mapbox_style="carto-darkmatter",
        zoom=9,
    )
    fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0})
    return fig


def create_line_chart(df, dwelling_type):
    include = df
    include["year_month"] = include["date"].dt.to_period("M").astype(str)
    include = (
        include.groupby(["year_month", "propertyTypeLabel"])["amount"]
        .mean()
        .reset_index()
    )
    fig = px.line(
        include,
        x="year_month",
        y="amount",
        color="propertyTypeLabel",
        labels={"year_month": "Year", "amount": "Sale Price"},
        title="Sale Price of Each Type of Dwelling from 2000 to Current Year",
    )
    return fig


def create_dwelling_chart(df):
    df["year"] = df["date"].dt.to_period("Y")
    df_group = (
        df.groupby(["year", "propertyTypeLabel"]).size().reset_index(name="count")
    )
    df_group["Total"] = df_group.groupby("year")["count"].transform("sum")
    df_group["Percentage"] = df_group["count"] / df_group["Total"] * 100
    last_5_years = df_group[df_group["year"] >= (df_group["year"].max() - 4)]
    last_5_years["year"] = last_5_years["year"].astype(str)

    fig = px.bar(
        last_5_years,
        x="Percentage",
        y="year",
        color="propertyTypeLabel",
        color_continuous_scale="Inferno",
        barmode="relative",
        orientation="h",
        labels={"Percentage": "Percentage Sales of Each Type of House", "Year": "Year"},
        title="Percentage of Each Type of Dwelling in the Last 5 Years",
    )
    return fig


def key_stats_df(df):
    include = df
    include["year_month"] = include["date"].dt.to_period("M").astype(str)
    latest_year_month = pd.to_datetime(df["year_month"]).max()
    months = (
        pd.date_range(end=latest_year_month, periods=3, freq="ME")
        .strftime("%Y-%m")
        .tolist()
    )
    include = (
        include.groupby(["year_month", "propertyTypeLabel"])["amount"]
        .mean()
        .reset_index()
    )
    df_pivot = include.pivot_table(
        index="propertyTypeLabel", columns="year_month", values="amount"
    ).reset_index()

    column_mapping = {
        months[0]: f"Average price in {(pd.to_datetime(months[0])).strftime('%B %Y')}",
        months[1]: f"Average price in {(pd.to_datetime(months[1])).strftime('%B %Y')}",
        months[2]: f"Average price in {(pd.to_datetime(months[2])).strftime('%B %Y')}",
    }
    df_pivot.rename(columns=column_mapping, inplace=True)

    previous_year = (latest_year_month - pd.DateOffset(years=1)).strftime("%Y-%m")
    df_pivot["Year-on-year change (£)"] = (
        df_pivot[column_mapping[months[2]]] - df_pivot[previous_year]
    ).apply(lambda x: f"£{x:+.2f}")
    df_pivot["Year-on-year change (%)"] = (
        (df_pivot[column_mapping[months[2]]] - df_pivot[previous_year])
        / df_pivot[previous_year]
        * 100
    ).apply(lambda x: f"{x:+.1f}%")

    df_final = df_pivot.loc[
        :,
        ["propertyTypeLabel"]
        + list(column_mapping.values())
        + ["Year-on-year change (£)", "Year-on-year change (%)"],
    ]
    df_final.rename(columns={"propertyTypeLabel": "Category"}, inplace=True)
    return df_final


# Setup page config
st.set_page_config(
    page_title="UK Houseprice Dashboard",
    page_icon="🏘️",
    layout="wide",
    initial_sidebar_state="auto",
)


# Setup side bar
with st.sidebar:
    st.title("UK Houseprice Dashboard 🏘️")

    st.subheader("Data Form", divider="gray")
    data_form = st.form("data")
    town = data_form.text_input("Town", "Wolverhampton")
    year = data_form.slider("Year for choropleth", 2000, 2024, 2024)
    submit_button = data_form.form_submit_button("Generate")

    st.subheader("About", divider="gray")
    st.write(
        """
      - Data: https://landregistry.data.gov.uk/
        """
    )


current_date = datetime.now().strftime("%Y-%m-%d")

# Streamlit app

if submit_button:
    sparql_query = query(town.upper(), current_date)
    df = return_data(sparql_query)
    df["date"] = pd.to_datetime(df["date"])

    col = st.columns((0.2, 0.8, 0.2), gap="small")
    with col[1]:
        key_stats = key_stats_df(df)
        st.subheader("Key Statistics", divider="gray")
        st.dataframe(key_stats, hide_index=True)
        st.subheader("Choropleth Plot", divider="gray")
        choropleth = create_choropleth_mapbox(df, year, town)
        if choropleth is not None:
            st.plotly_chart(choropleth)

    st.subheader("Graph Plots", divider="gray")
    col2 = st.columns((0.5, 0.5))
    with col2[0]:
        scatter = create_line_chart(df, "Semi-detached")
        if scatter is not None:
            st.plotly_chart(scatter)
    with col2[1]:
        barchart = create_dwelling_chart(df)
        if barchart is not None:
            st.plotly_chart(barchart)

    st.info("Change dwelling types shown using the key", icon="ℹ️")
