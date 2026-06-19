import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import gpxpy
from geopy.distance import geodesic
import xml.etree.ElementTree as ET

st.set_page_config(layout="wide")

st.title("Bozeman Stop Aheads")

SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTWDDqZ0Qu0WLj0va46qBEvMQvh39mCNHf8q2QU1U52cl1sgMP-ugF_PokPcrNfks5KsEOGW8Hx4yRS/pub?output=csv"

MAX_DISTANCE_METERS_DEFAULT = 50


def extract_lat_lon(url):
    url = str(url)

    match = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", url)
    if match:
        return float(match.group(1)), float(match.group(2))

    match = re.search(r"[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)", url)
    if match:
        return float(match.group(1)), float(match.group(2))

    return None, None


def clean_column_names(df):
    df = df.copy()
    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
        .str.replace(" ", "_")
        .str.replace("-", "_")
    )
    return df


def parse_gpx(uploaded_file):
    gpx = gpxpy.parse(uploaded_file)
    points = []

    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                points.append((point.latitude, point.longitude))

    for route in gpx.routes:
        for point in route.points:
            points.append((point.latitude, point.longitude))

    return points


def cumulative_route_distances(route_points):
    distances = [0.0]
    total = 0.0

    for i in range(1, len(route_points)):
        total += geodesic(route_points[i - 1], route_points[i]).meters
        distances.append(total)

    return distances


def find_nearby_signs(df_signs, route_points, max_distance_m):
    route_distances = cumulative_route_distances(route_points)
    matches = []

    for _, sign in df_signs.iterrows():
        sign_coord = (sign["lat"], sign["lon"])

        best_distance = float("inf")
        best_route_index = None

        for i, route_point in enumerate(route_points):
            d = geodesic(sign_coord, route_point).meters

            if d < best_distance:
                best_distance = d
                best_route_index = i

        if best_distance <= max_distance_m:
            distance_along_m = route_distances[best_route_index]

            matches.append({
                "name": sign["name"],
                "sign_type": sign.get("sign_type", ""),
                "lat": sign["lat"],
                "lon": sign["lon"],
                "distance_to_route_m": round(best_distance, 1),
                "distance_along_route_km": round(distance_along_m / 1000, 2),
                "distance_along_route_mi": round(distance_along_m / 1609.344, 2),
            })

    if not matches:
        return pd.DataFrame(columns=[
            "name",
            "sign_type",
            "lat",
            "lon",
            "distance_to_route_m",
            "distance_along_route_km",
            "distance_along_route_mi",
        ])

    return pd.DataFrame(matches).sort_values("distance_along_route_km")


def make_waypoints_gpx(matched_df):
    gpx = ET.Element(
        "gpx",
        version="1.1",
        creator="Bozeman Stop Aheads"
    )

    for _, row in matched_df.iterrows():
        wpt = ET.SubElement(
            gpx,
            "wpt",
            lat=str(row["lat"]),
            lon=str(row["lon"])
        )

        name = ET.SubElement(wpt, "name")
        name.text = str(row["name"])

        desc = ET.SubElement(wpt, "desc")
        desc.text = (
            f"Stop Ahead - {row['distance_along_route_km']} km / "
            f"{row['distance_along_route_mi']} mi"
        )

        symbol = ET.SubElement(wpt, "sym")
        symbol.text = "Flag"

    return ET.tostring(
        gpx,
        encoding="utf-8",
        xml_declaration=True
    )


@st.cache_data(ttl=60)
def load_signs():
    df = pd.read_csv(SHEET_URL)
    df = clean_column_names(df)

    if "google_maps_url" in df.columns and "maps_url" not in df.columns:
        df = df.rename(columns={"google_maps_url": "maps_url"})

    if "map_url" in df.columns and "maps_url" not in df.columns:
        df = df.rename(columns={"map_url": "maps_url"})

    required_columns = ["name", "maps_url"]

    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        st.error(f"Missing required column(s): {missing}")
        st.write("Columns found in your Google Sheet:")
        st.write(df.columns.tolist())
        st.stop()

    if "sign_type" not in df.columns:
        df["sign_type"] = "stop ahead"

    df["lat"] = df["maps_url"].apply(lambda x: extract_lat_lon(x)[0])
    df["lon"] = df["maps_url"].apply(lambda x: extract_lat_lon(x)[1])

    df_valid = df.dropna(subset=["lat", "lon"]).copy()
    df_valid["lat"] = df_valid["lat"].astype(float)
    df_valid["lon"] = df_valid["lon"].astype(float)

    return df_valid


df_valid = load_signs()

st.sidebar.header("Route Matching")

uploaded_gpx = st.sidebar.file_uploader("Upload GPX route", type=["gpx"])

max_distance_m = st.sidebar.slider(
    "Match signs within this distance from route",
    min_value=10,
    max_value=150,
    value=MAX_DISTANCE_METERS_DEFAULT,
    step=10,
)

st.sidebar.metric("Known stop aheads", len(df_valid))

route_points = None
matched_df = pd.DataFrame()

if uploaded_gpx is not None:
    route_points = parse_gpx(uploaded_gpx)

    if len(route_points) < 2:
        st.error("This GPX file does not contain enough route points.")
        st.stop()

    matched_df = find_nearby_signs(df_valid, route_points, max_distance_m)

    st.sidebar.metric("Matched on route", len(matched_df))

    if not matched_df.empty:
        st.sidebar.subheader("Upcoming Stop Aheads")

        for _, row in matched_df.iterrows():
            st.sidebar.write(
                f"**{row['name']}** — "
                f"{row['distance_along_route_km']} km / "
                f"{row['distance_along_route_mi']} mi"
            )

if route_points:
    map_start = route_points[0]
    zoom = 12
else:
    map_start = [df_valid["lat"].mean(), df_valid["lon"].mean()]
    zoom = 11

m = folium.Map(location=map_start, zoom_start=zoom)

if route_points:
    folium.PolyLine(
        route_points,
        weight=5,
        tooltip="Uploaded route",
    ).add_to(m)

stop_ahead_icon_html = """
<div style="
    font-size: 28px;
    transform: translate(-50%, -50%);
">
    ⚠️
</div>
"""

matched_names = set(matched_df["name"]) if not matched_df.empty else set()

for _, row in df_valid.iterrows():
    icon = folium.DivIcon(
        html=stop_ahead_icon_html,
        icon_size=(30, 30),
        icon_anchor=(15, 15),
    )

    is_matched = row["name"] in matched_names

    popup = f"""
    <b>{row.get('name', 'Unnamed sign')}</b><br>
    Type: {row.get('sign_type', '')}<br>
    """

    if is_matched:
        match_row = matched_df[matched_df["name"] == row["name"]].iloc[0]
        popup += f"""
        Distance along route: {match_row['distance_along_route_km']} km / {match_row['distance_along_route_mi']} mi<br>
        Distance from route: {match_row['distance_to_route_m']} m
        """

    folium.Marker(
        [row["lat"], row["lon"]],
        popup=popup,
        tooltip=str(row.get("name", "Unnamed sign")),
        icon=icon,
    ).add_to(m)

st_folium(m, width=1200, height=700)

if uploaded_gpx is not None:
    st.subheader("Upcoming Stop Aheads on Route")
    st.write(f"Matched signs found: {len(matched_df)}")

    if matched_df.empty:
        st.info("No stop aheads matched this route. Try increasing the match distance.")
    else:
        st.dataframe(matched_df)

        waypoints_gpx = make_waypoints_gpx(matched_df)

        st.download_button(
            label="Download Garmin Waypoints GPX",
            data=waypoints_gpx,
            file_name="stop_aheads_waypoints.gpx",
            mime="application/gpx+xml",
        )

st.subheader("Full Stop Ahead Database")
st.dataframe(df_valid)