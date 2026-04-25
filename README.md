# AIS Ship Tracker

A real-time maritime vessel tracker for the terminal, built in Python using the [AISStream](https://aisstream.io) WebSocket API. Displays a live color-coded table of ships including vessel type, flag, destination, speed, heading, and navigational status — with automatic reconnection and persistent session support via tmux.

Built and tested on a Raspberry Pi 5 running Debian/Raspberry Pi OS.

![Python](https://img.shields.io/badge/python-3.13-blue) ![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi%205-red) ![License](https://img.shields.io/badge/license-MIT-green)

---

## Features

- Live WebSocket feed from AISStream with automatic reconnection
- Color-coded vessel rows by type (tanker, cargo, passenger, tug, SAR, fishing, sailing, etc.)
- Per-vessel cache merging position reports and static data (name, type, destination, dimensions, draught, ETA, callsign, IMO)
- MMSI decoding → country/flag of registration using full ITU Maritime Identification Digits table
- Navigational status decoding (underway, moored, at anchor, restricted manoeuvrability, etc.)
- Stale vessel dimming (rows fade after 60 seconds without an update)
- Live-redrawing terminal table with fixed header — no scrolling noise
- Predefined regions switchable via `--region` command-line flag
- Custom bounding box support via `--bbox`
- Adjustable table size via `--table`

---

## Requirements

- Python 3.10+
- A free API key from [aisstream.io](https://aisstream.io)
- A terminal supporting ANSI 256 colors (xterm-256color recommended)

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Setup

**1. Clone the repo:**
```bash
git clone https://github.com/jeffg38/ais_SHIPTRACKER.git
cd ais_SHIPTRACKER
```

**2. Create a virtual environment:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**3. Install dependencies:**
```bash
pip install -r requirements.txt
```

**4. Create your `.env` file with your AISStream API key:**
```bash
nano .env
```
Add this line:
```
AISSTREAM_API_KEY=your_api_key_here
```
Get a free API key at [aisstream.io](https://aisstream.io). The `.env` file is listed in `.gitignore` and will never be committed to the repo.

---

## Usage

**Basic — English Channel (default):**
```bash
python ais_SHIPTRACKER.py
```

**Select a predefined region:**
```bash
python ais_SHIPTRACKER.py --region channel      # English Channel / Dover Strait
python ais_SHIPTRACKER.py --region gulf         # Persian Gulf / Strait of Hormuz
python ais_SHIPTRACKER.py --region northsea     # North Sea
python ais_SHIPTRACKER.py --region med          # Mediterranean Sea
python ais_SHIPTRACKER.py --region singapore    # Singapore Strait
```

**Custom bounding box:**
```bash
python ais_SHIPTRACKER.py --region custom --bbox "48.0 52.0 -5.0 2.0"
# Format: "LAT_MIN LAT_MAX LON_MIN LON_MAX"
```

**Change table size:**
```bash
python ais_SHIPTRACKER.py --region channel --table 30
```

**Show help:**
```bash
python ais_SHIPTRACKER.py --help
```

---

## Running Long-Term on a Raspberry Pi

For persistent 24/7 operation use `tmux` so the script keeps running even if your SSH session drops:

**Install tmux (first time only):**
```bash
sudo apt install tmux
```

**Start a named session and run the tracker:**
```bash
tmux new -s ais
cd ais_SHIPTRACKER
source venv/bin/activate
python ais_SHIPTRACKER.py
```

**Detach and leave it running** (script continues in background):
```
Ctrl+B, then D
```

**Reattach later to check on it:**
```bash
tmux attach -t ais
```

**List all running tmux sessions:**
```bash
tmux ls
```

---

## SSH Keepalive (Mac/Linux)

If you're connecting to your Pi over SSH and your connection drops when idle, add this to `~/.ssh/config` on your local machine:

```
Host 192.168.0.xx          # replace with your Pi's IP
    ServerAliveInterval 60
    ServerAliveCountMax 10
```

---

## Color Key

| Color | Vessel Type |
|---|---|
| 🟡 Yellow | Tanker |
| ⚪ White | Cargo |
| 🔵 Cyan | Passenger / High-speed craft |
| 🟠 Orange | Tug / Towing |
| 🟢 Green | Fishing |
| 🟣 Magenta | Sailing / Pleasure craft |
| 🔴 Red | SAR / Military / Law enforcement |
| 💙 Blue | Pilot vessel |
| ⬜ Grey | Unknown type |
| Dim | Stale — no update in >60 seconds |

---

## Table Columns

| Column | Description |
|---|---|
| Name | Vessel name from AIS |
| Flag | Country of registration decoded from MMSI |
| Type | Vessel type from ShipStaticData |
| Destination | Destination port (UN/LOCODE or free text) |
| Lat / Lon | Current position in decimal degrees |
| SOG | Speed Over Ground in knots |
| HDG | True heading in degrees (C = Course Over Ground fallback) |
| Nav Status | AIS navigational status |
| Age | Seconds since last message received |
| # | Total messages received from this vessel this session |

---

## Data Notes

- **Vessel type** comes from `ShipStaticData` messages which are broadcast every few minutes. Type colors will fill in within 2–3 minutes of startup.
- **Destinations** use [UN/LOCODE](https://unece.org/trade/uncefact/unlocode) format (e.g. `NLRTM` = Rotterdam, `BEANR` = Antwerp, `FRDKK` = Dunkirk) or free text entered by the crew.
- **511 heading** means "not available" per the AIS spec — the script falls back to Course Over Ground (shown with a `C` suffix) automatically.
- **AIS coverage** varies by region. The English Channel and Singapore Strait have excellent terrestrial receiver coverage. The Persian Gulf has patchy coverage — expect fewer hits.
- **Flags of convenience** are common — Marshall Islands, Liberia, Panama, and Malta flags on vessels with European or Asian operators are normal.

---

## Planned Features

- Flask/HTTP JSON server for feeding vessel data to an Adafruit Matrix Portal S3 + 64×64 RGB LED matrix display
- Pre-computed coastline bitmap for real-time map rendering on the LED matrix
- Scrolling ship name/destination ticker on the LED display
- CSV/SQLite logging for track history

---

## Project Background

Developed iteratively on a Raspberry Pi 5 in Denver, CO. The English Channel / Dover Strait bounding box `[50.5,1.0]→[51.5,2.5]` covers one of the busiest shipping lanes in the world and provides a rich real-time data stream for development and testing.

---

## License

MIT
