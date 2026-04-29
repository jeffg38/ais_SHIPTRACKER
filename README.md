# AIS Ship Tracker + LED Matrix Display

A real-time maritime vessel tracking system built on a Raspberry Pi 5, displaying live ship traffic in the English Channel on a 64×64 RGB LED matrix panel. Vessels are color-coded by type, positioned on a geographic map with coastline reference, and identified by a scrolling ticker with type codes, destination, speed, heading, and nav status.

![Python](https://img.shields.io/badge/python-3.13-blue) ![CircuitPython](https://img.shields.io/badge/circuitpython-9.x-green) ![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi%205-red) ![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## System Overview

```
AISStream WebSocket API
        │
        ▼
Raspberry Pi 5 (Skadi)
  ├── ais_SHIPTRACKER.py   — live AIS data, vessel cache, vessels.json writer
  └── ais_server.py        — Flask HTTP server serving vessels.json on port 5000
        │
        │  WiFi / HTTP (local network)
        ▼
Adafruit Matrix Portal S3
  └── code.py              — CircuitPython display driver
        │
        ▼
64×64 RGB LED Matrix Panel (Adafruit #5362, 2mm pitch)
```

---

## Hardware

| Component | Part | Notes |
|---|---|---|
| Single-board computer | Raspberry Pi 5 | Any Pi 4/5 works |
| Matrix controller | Adafruit Matrix Portal S3 | Built-in WiFi, ESP32-S3 |
| LED panel | Adafruit #5362 — 64×64 RGB, 2mm pitch | HUB75 interface |
| Power supply | 5V 3A USB-C | Sufficient for this low pixel-fill display |

**Important hardware note:** The Matrix Portal S3 Address E jumper must be bridged to pin 8 for 64-row panels. On most boards this is already done at the factory — check the two pads labeled `8` and `16` on the back of the board. The middle pad should be connected to `8`.

---

## Display Layout

```
┌──────────────────────────────────────┐  row 0
│  UK / Kent coastline (dark green)    │
│                                      │
│  M A P   A R E A   (rows 0–54)       │
│                                      │
│  Colored dots = vessels              │
│  City markers = warm white +         │
│    Folkestone · Dover · Ramsgate     │
│    Boulogne · Calais · Dunkirk       │
│                                      │
│  French/Belgian coastline            │
├──────────────────────────────────────┤  row 55
│  ── divider ─────────────────────── │
├──────────────────────────────────────┤  row 56
│  Scrolling ticker (rows 56–63)       │
│  TK BIRTHE ESSBERGER>BEANR 9.4kn 58 │
└──────────────────────────────────────┘  row 63
```

---

## Vessel Color Key

| Color | Type |
|---|---|
| Yellow | Tanker |
| Orange | Cargo |
| Cyan | Passenger / High-speed craft |
| Amber | Tug / Towing |
| Green | Fishing |
| Magenta | Sailing / Pleasure |
| Red | SAR / Military |
| Blue | Pilot vessel |
| Grey | Unknown type |
| Dim | Stale — no update in >5 minutes |

---

## Ticker Format

Each vessel entry in the scrolling ticker shows:

```
TK BIRTHE ESSBERGER>BEANR 9.4kn 58   CG DOVER SEAWAYS>DUNKER 16.4kn 79 MOOR
```

| Field | Example | Meaning |
|---|---|---|
| Type code | `TK` | Vessel type (TK=Tanker, CG=Cargo, PS=Passenger, TG=Tug, FV=Fishing, SV=Sailing, SR=SAR, PV=Pilot, HS=High-speed) |
| Name | `BIRTHE ESSBERGER` | Vessel name |
| Destination | `>BEANR` | UN/LOCODE or free-text destination |
| SOG | `9.4kn` | Speed over ground in knots |
| HDG | `58` | Heading in degrees |
| Nav status | `MOOR` | Only shown when notable (ANCH, MOOR, RESTR, DRGHT, AGRND, FISH, EMRG) |

---

## Button Functions (Matrix Portal S3)

| Button | Action |
|---|---|
| UP | Show color key overlay (6 seconds) |
| DOWN | Show stats screen — vessel count, message count, uptime, errors, server IP |

---

## Software Setup

### Raspberry Pi

**1. Clone the repo:**
```bash
git clone https://github.com/jeffg38/ais_SHIPTRACKER.git
cd ais_SHIPTRACKER
```

**2. Create virtual environment and install dependencies:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**3. Create `.env` file with your AISStream API key:**
```bash
nano .env
```
```
AISSTREAM_API_KEY=your_api_key_here
```
Get a free API key at [aisstream.io](https://aisstream.io).

**4. Run the tracker and server in separate tmux sessions:**
```bash
# Session 1 — AIS tracker
tmux new -s ais
source venv/bin/activate
python ais_SHIPTRACKER.py --region channel

# Session 2 — Flask server
tmux new -s server
source venv/bin/activate
python ais_server.py
```

**5. Verify the server is running:**

Open `http://[PI-IP]:5000/status` in a browser. You should see a live vessel table auto-refreshing every 10 seconds.

**Detach from tmux** with `Ctrl+B, D`. Sessions persist after SSH disconnect.
**Reattach** with `tmux attach -t ais` or `tmux attach -t server`.

---

### Matrix Portal S3

**1. Install CircuitPython** on the Matrix Portal S3:
- Double-click the reset button until the NeoPixel turns green
- Download the latest CircuitPython UF2 from [circuitpython.org](https://circuitpython.org/board/adafruit_matrixportal_s3/)
- Drag the UF2 onto the MATRIXPORTAL drive

**2. Install required libraries** into `/lib` on CIRCUITPY:

From the [Adafruit CircuitPython Bundle](https://circuitpython.org/libraries):
- `adafruit_display_text/` (folder)
- `adafruit_requests.mpy`
- `adafruit_connection_manager.mpy`

**3. Configure WiFi and server settings:**

Copy `settings.toml.example` to `settings.toml` on CIRCUITPY and fill in your details:
```toml
CIRCUITPY_WIFI_SSID = "your_wifi_network"
CIRCUITPY_WIFI_PASSWORD = "your_wifi_password"
AIS_SERVER_IP = "192.168.0.51"
AIS_SERVER_PORT = "5000"
```

**4. Copy `code.py`** to the root of CIRCUITPY:
```bash
cp code.py /Volumes/CIRCUITPY/code.py
```

The Matrix Portal S3 will restart automatically and connect to the Pi server.

---

## Regions

The tracker supports multiple predefined regions via the `--region` flag:

```bash
python ais_SHIPTRACKER.py --region channel      # English Channel (default)
python ais_SHIPTRACKER.py --region gulf         # Persian Gulf / Strait of Hormuz
python ais_SHIPTRACKER.py --region northsea     # North Sea
python ais_SHIPTRACKER.py --region med          # Mediterranean Sea
python ais_SHIPTRACKER.py --region singapore    # Singapore Strait
python ais_SHIPTRACKER.py --region custom --bbox "50.5 51.5 1.0 2.5"
```

**Note:** The `code.py` bounding box constants (`LAT_MIN`, `LAT_MAX`, `LON_MIN`, `LON_MAX`) and coastline bitmap must be updated manually to match the chosen region. The English Channel configuration is the default.

---

## SSH Keepalive (recommended)

Add to `~/.ssh/config` on your local machine to prevent idle SSH disconnections:

```
Host [PI-IP]
    ServerAliveInterval 60
    ServerAliveCountMax 10
```

---

## Project Background

Built iteratively on a Raspberry Pi 5 in Denver, CO, monitoring real-time ship traffic in the Dover Strait — one of the busiest shipping lanes in the world. The English Channel bounding box `[50.5–51.5°N, 1.0–2.5°E]` captures the full Traffic Separation Scheme, both traffic lanes, all major ferry routes, offshore wind farm service vessels, and the ports of Dover, Folkestone, Ramsgate, Calais, Dunkirk, and Boulogne.

---

## License

MIT
