import dash
import dash_leaflet as dl
from dash import dcc
from dash import html
from dash.dependencies import Input, Output
import pandas as pd
from influxdb_client import InfluxDBClient
from datetime import datetime, timezone
import time
import os


# -------------------------
# Configuration
# -------------------------
# InfluxDB Cloud credentials
INFLUX_TOKEN = os.environ.get("INFLUX_TOKEN")
INFLUX_URL = os.environ.get("INFLUX_URL")
INFLUX_ORG = os.environ.get("INFLUX_ORG")
INFLUX_BUCKET = "ls300-tracking-demo"

MEASUREMENT = "tracker_data"
FRIDAY_START = "2025-05-30T06:00:00Z"  # Adjust as needed

# -------------------------
# Connect to InfluxDB
# -------------------------
client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
query_api = client.query_api()

# -------------------------
# Load all data from Friday
# -------------------------
def load_all_data():
    query = f'''
    from(bucket: "{INFLUX_BUCKET}")
      |> range(start: {FRIDAY_START})
      |> filter(fn: (r) => r._measurement == "{MEASUREMENT}")
      |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
      |> keep(columns: ["_time", "device", "latitude", "longitude", "temperature", "humidity", "speed", "altitude", "pressure", "batteryVoltage", "counter", "heading", "hoursUptime", "satId", "userButton", "hall"])
    '''
    df = query_api.query_data_frame(query)
    df = df.rename(columns={"_time": "time"})
    df["time"] = pd.to_datetime(df["time"])
    return df

# Global data store
data_df = load_all_data()

# -------------------------
# Create Dash App
# -------------------------
app = dash.Dash(__name__)
app.title = "LS300 Tracker Demo"
server = app.server

# Map centre (you can make this dynamic later)
map_center = [data_df["latitude"].mean(), data_df["longitude"].mean()]

app.layout = html.Div([
    html.H2("Lacuna Space Tracker Demo"),
    dl.Map(center=map_center, zoom=12, id="live-map", style={'width': '100%', 'height': '90vh'}, children=[
        dl.TileLayer(),
        dl.LayerGroup(id="marker-layer")
    ]),
    dcc.Interval(id="interval", interval=30*1000, n_intervals=0)
])

# -------------------------
# Helper to format hover popup
# -------------------------
def format_popup(row):
    return html.Div([
        html.B(f"Device: {row['device']}"),
        html.Br(),
        f"Time: {row['time'].strftime('%Y-%m-%d %H:%M:%S')}",
        html.Br(),
        f"Temp: {row.get('temperature', 'N/A')}°C",
        html.Br(),
        f"Humidity: {row.get('humidity', 'N/A')}%",
        html.Br(),
        f"Speed: {row.get('speed', 'N/A')} m/s",
        html.Br(),
        f"Pressure: {row.get('pressure', 'N/A')} hPa",
        html.Br(),
        f"Battery: {row.get('batteryVoltage', 'N/A')} V"
    ])

# -------------------------
# Callback to update map
# -------------------------
@app.callback(
    Output("marker-layer", "children"),
    Input("interval", "n_intervals")
)
def update_map(n):
    global data_df
    # Query new data
    last_time = data_df["time"].max().isoformat()
    query = f'''
    from(bucket: "{INFLUX_BUCKET}")
      |> range(start: time(v: "{last_time}"))
      |> filter(fn: (r) => r._measurement == "{MEASUREMENT}")
      |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
      |> keep(columns: ["_time", "device", "latitude", "longitude", "temperature", "humidity", "speed", "altitude", "pressure", "batteryVoltage", "counter", "heading", "hoursUptime", "satId", "userButton", "hall"])
    '''
    new_df = query_api.query_data_frame(query)
    if not new_df.empty:
        new_df = new_df.rename(columns={"_time": "time"})
        new_df["time"] = pd.to_datetime(new_df["time"])
        data_df = pd.concat([data_df, new_df], ignore_index=True)

    # Build markers
    markers = []
    for _, row in data_df.iterrows():
        if pd.notna(row["latitude"]) and pd.notna(row["longitude"]):
            markers.append(
                dl.CircleMarker(
                    center=(row["latitude"], row["longitude"]),
                    radius=4,
                    color="blue",
                    fill=True,
                    fillOpacity=0.7,
                    children=dl.Tooltip(children=format_popup(row))
                )
            )
    return markers

# -------------------------
# Run the app
# -------------------------
if __name__ == '__main__':
    app.run(debug=True)