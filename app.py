import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re

st.set_page_config(layout="wide")

st.title("Bozeman Stop Ahead Database")

def extract_lat_lon(url):
    match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', url)

    if match:
        return float(match.group(1)), float(match.group(2))

    return None, None

df = pd.read_csv("signs.csv")

df["lat"] = None
df["lon"] = None

for idx, row in df.iterrows():
    lat, lon = extract_lat_lon(str(row["maps_url"]))

    df.loc[idx, "lat"] = lat
    df.loc[idx, "lon"] = lon

st.write(f"Loaded {len(df)} stop ahead locations")

center_lat = df["lat"].astype(float).mean()
center_lon = df["lon"].astype(float).mean()

m = folium.Map(
    location=[center_lat, center_lon],
    zoom_start=11
)

for _, row in df.iterrows():
    if pd.notna(row["lat"]) and pd.notna(row["lon"]):
        folium.Marker(
            [float(row["lat"]), float(row["lon"])],
            popup=row["name"]
        ).add_to(m)

st_folium(m, width=1200, height=700)

st.subheader("Database")

st.dataframe(df)