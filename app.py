import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re

st.set_page_config(layout="wide")

st.title("Bozeman Stop Ahead Database")

def extract_lat_lon(url):
    url = str(url)

    match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if match:
        return float(match.group(1)), float(match.group(2))

    match = re.search(r'[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if match:
        return float(match.group(1)), float(match.group(2))

    return None, None

df = pd.read_csv("signs.csv")

if "maps_url" not in df.columns:
    st.error("Your signs.csv must have a column named maps_url.")
    st.stop()

df["lat"] = df["maps_url"].apply(lambda x: extract_lat_lon(x)[0])
df["lon"] = df["maps_url"].apply(lambda x: extract_lat_lon(x)[1])

invalid_count = df["lat"].isna().sum()

df_valid = df.dropna(subset=["lat", "lon"]).copy()
df_valid["lat"] = df_valid["lat"].astype(float)
df_valid["lon"] = df_valid["lon"].astype(float)

st.write(f"Loaded {len(df_valid)} valid stop ahead locations")

if invalid_count > 0:
    st.warning(f"{invalid_count} row(s) could not be mapped because the Google Maps URL did not contain coordinates.")

if df_valid.empty:
    st.error("No valid sign coordinates found.")
    st.stop()

center_lat = df_valid["lat"].mean()
center_lon = df_valid["lon"].mean()

m = folium.Map(
    location=[center_lat, center_lon],
    zoom_start=11
)

stop_ahead_icon_html = """
<div style="
    font-size: 28px;
    transform: translate(-50%, -50%);
">
    ⚠️
</div>
"""

for _, row in df_valid.iterrows():
    icon = folium.DivIcon(
        html=stop_ahead_icon_html,
        icon_size=(30, 30),
        icon_anchor=(15, 15)
    )

    popup = f"""
    <b>{row.get('name', 'Unnamed sign')}</b><br>
    Type: {row.get('sign_type', '')}
    """

    folium.Marker(
        [row["lat"], row["lon"]],
        popup=popup,
        tooltip=str(row.get("name", "Unnamed sign")),
        icon=icon
    ).add_to(m)

st_folium(m, width=1200, height=700)

st.subheader("Database")
st.dataframe(df_valid)