#!/usr/bin/env python3
"""
ais_server.py — AIS Vessel Data HTTP Server
Serves vessels.json to the Matrix Portal S3 over local WiFi.

Run this on the Pi alongside ais_SHIPTRACKER.py:
    python ais_server.py

The Matrix Portal S3 polls:
    http://192.168.x.xxx:5000/vessels.json

Endpoints:
    GET /vessels.json   — full vessel data for the S3
    GET /status         — human-readable status page
    GET /               — same as /status
"""

from flask import Flask, jsonify, send_file, render_template_string
import json
import os
import time

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
JSON_PATH   = "/home/jeffg38/ais_project/vessels.json"
HOST        = "0.0.0.0"    # listen on all interfaces
PORT        = 5000
server_start = time.time()

app = Flask(__name__)

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def load_vessels():
    """Load and return the vessels.json payload, or None if unavailable."""
    try:
        with open(JSON_PATH, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None


def file_age():
    """Return age of vessels.json in seconds, or None if missing."""
    try:
        return int(time.time() - os.path.getmtime(JSON_PATH))
    except FileNotFoundError:
        return None


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@app.route("/vessels.json")
def vessels():
    """
    Main endpoint — polled by the Matrix Portal S3.
    Returns JSON with vessel list and bounding box metadata.
    If the file is missing or stale (>60s), returns an error payload.
    """
    data = load_vessels()
    age  = file_age()

    if data is None:
        return jsonify({
            "error":   "vessels.json not found",
            "hint":    "Is ais_SHIPTRACKER.py running?",
            "count":   0,
            "vessels": [],
        }), 503

    if age and age > 60:
        # File exists but is stale — tracker may have crashed
        data["warning"] = f"Data is {age}s old — tracker may be down"

    return jsonify(data)


STATUS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>AIS Server Status</title>
  <meta http-equiv="refresh" content="10">
  <style>
    body { font-family: monospace; background: #0a0a0a; color: #00cc44;
           padding: 2rem; max-width: 800px; margin: 0 auto; }
    h1   { color: #00ff55; border-bottom: 1px solid #1a4a1a; padding-bottom: 0.5rem; }
    .ok  { color: #00cc44; }
    .warn{ color: #ffaa00; }
    .err { color: #ff4444; }
    table{ border-collapse: collapse; width: 100%; margin-top: 1rem; }
    th   { text-align: left; color: #888; padding: 4px 12px; font-weight: normal; }
    td   { padding: 4px 12px; border-bottom: 1px solid #1a2a1a; }
    .dim { color: #555; }
  </style>
</head>
<body>
  <h1>🚢 AIS Server</h1>
  <p>Server uptime: <b>{{ uptime }}</b> &nbsp;|&nbsp;
     Auto-refreshes every 10s &nbsp;|&nbsp;
     <a href="/vessels.json" style="color:#00aaff">View raw JSON</a></p>

  {% if error %}
    <p class="err">⚠️ {{ error }}</p>
  {% else %}
    <p class="ok">✅ Serving {{ count }} vessels from {{ region }}</p>
    <p class="dim">Data age: {{ age }}s &nbsp;|&nbsp;
       Bounding box: [{{ lat_min }},{{ lon_min }}] → [{{ lat_max }},{{ lon_max }}]</p>

    <table>
      <tr>
        <th>#</th><th>Name</th><th>Type</th><th>Flag</th>
        <th>Destination</th><th>Lat</th><th>Lon</th>
        <th>SOG</th><th>HDG</th><th>Age</th>
      </tr>
      {% for v in vessels %}
      <tr>
        <td class="dim">{{ loop.index }}</td>
        <td>{{ v.name }}</td>
        <td>{{ v.type }}</td>
        <td class="dim">{{ v.flag }}</td>
        <td class="dim">{{ v.dest }}</td>
        <td class="dim">{{ v.lat }}</td>
        <td class="dim">{{ v.lon }}</td>
        <td>{{ v.sog }}kn</td>
        <td class="dim">{{ v.hdg }}</td>
        <td class="{{ 'warn' if v.age > 60 else 'ok' }}">{{ v.age }}s</td>
      </tr>
      {% endfor %}
    </table>
  {% endif %}
</body>
</html>
"""


@app.route("/")
@app.route("/status")
def status():
    """Human-readable status page — auto-refreshes every 10 seconds."""
    data  = load_vessels()
    age   = file_age()
    uptime_s = int(time.time() - server_start)
    uptime = f"{uptime_s // 3600}h {(uptime_s % 3600) // 60}m {uptime_s % 60}s"

    if data is None:
        return render_template_string(
            STATUS_TEMPLATE,
            error="vessels.json not found — is ais_SHIPTRACKER.py running?",
            uptime=uptime, count=0, region="", age=0,
            lat_min=0, lat_max=0, lon_min=0, lon_max=0, vessels=[],
        )

    return render_template_string(
        STATUS_TEMPLATE,
        error=None,
        uptime=uptime,
        count=data.get("count", 0),
        region=data.get("region", ""),
        age=age,
        lat_min=data.get("lat_min"), lat_max=data.get("lat_max"),
        lon_min=data.get("lon_min"), lon_max=data.get("lon_max"),
        vessels=data.get("vessels", [])[:50],  # cap at 50 rows for readability
    )


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n🚢  AIS Vessel Data Server")
    print(f"    Serving : {JSON_PATH}")
    print(f"    URL     : http://192.168.0.51:{PORT}/vessels.json")
    print(f"    Status  : http://192.168.0.51:{PORT}/status")
    print(f"    Press Ctrl+C to stop\n")

    # Check if the JSON file already exists
    if os.path.exists(JSON_PATH):
        age = file_age()
        print(f"    vessels.json found (age: {age}s)")
    else:
        print(f"    ⚠️  vessels.json not found yet — start ais_SHIPTRACKER.py first")

    app.run(host=HOST, port=PORT, debug=False)
