#!/usr/bin/env python3
"""
AISStream Vessel Tracker
Usage:
    python ais_tracker.py --region channel      # English Channel (default)
    python ais_tracker.py --region gulf         # Persian Gulf / Strait of Hormuz
    python ais_tracker.py --region northsea     # North Sea
    python ais_tracker.py --region med          # Mediterranean
    python ais_tracker.py --region singapore    # Singapore Strait
    python ais_tracker.py --region custom --bbox "LAT_MIN LAT_MAX LON_MIN LON_MAX"
"""

import websocket
import json
import time
import sys
import argparse
import os
from dotenv import load_dotenv

# ─────────────────────────────────────────────
# API KEY
# ─────────────────────────────────────────────
load_dotenv()
API_KEY = os.environ.get("AISSTREAM_API_KEY", "")

# How many vessels to show in the live table
TABLE_SIZE = 25

# ─────────────────────────────────────────────
# REGIONS
# ─────────────────────────────────────────────
REGIONS = {
    "channel":   (50.5,  51.5,   1.0,   2.5,  "English Channel"),
    "gulf":      (18.0,  32.0,  45.0,  62.0,  "Persian Gulf / Strait of Hormuz"),
    "northsea":  (51.0,  58.0,   2.0,   9.0,  "North Sea"),
    "med":       (30.0,  46.0,  -6.0,  37.0,  "Mediterranean Sea"),
    "singapore": ( 1.0,   2.0, 103.0, 105.0,  "Singapore Strait"),
    "ais":       (-90.0, 90.0, -180.0, 180.0, "Global (all AIS)"),
}

# ─────────────────────────────────────────────
# ANSI COLOR CODES
# ─────────────────────────────────────────────
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    # Foreground colors
    WHITE   = "\033[97m"
    YELLOW  = "\033[93m"
    CYAN    = "\033[96m"
    GREEN   = "\033[92m"
    MAGENTA = "\033[95m"
    BLUE    = "\033[94m"
    RED     = "\033[91m"
    ORANGE  = "\033[33m"
    GREY    = "\033[90m"
    BROWN   = "\033[38;5;94m"

# Map vessel type string → ANSI color
TYPE_COLOR = {
    "Tanker":          C.YELLOW,
    "Cargo":           C.BROWN,
    "Passenger":       C.CYAN,
    "Tug":             C.ORANGE,
    "Towing":          C.ORANGE,
    "Towing (large)":  C.ORANGE,
    "Fishing":         C.GREEN,
    "Pilot vessel":    C.BLUE,
    "Search & Rescue": C.RED,
    "Military":        C.RED,
    "Law enforcement": C.RED,
    "Sailing":         C.MAGENTA,
    "Pleasure craft":  C.MAGENTA,
    "High-speed craft":C.CYAN,
    "Dredging":        C.ORANGE,
    "Port tender":     C.ORANGE,
    "Medical":         C.RED,
    "—":               C.GREY,
}

def vessel_color(vtype, nav=None):
    """Return ANSI color for a vessel.
    - Known type → type color
    - Unknown type but nav status gives a hint → use that
    - Unknown type → white (grey is reserved for stale rows only)
    """
    if vtype and vtype != "—":
        return TYPE_COLOR.get(vtype, C.WHITE)
    # Use nav status as a fallback hint
    if nav:
        nl = nav.lower()
        if "fishing"  in nl: return C.GREEN
        if "sailing"  in nl: return C.MAGENTA
        if "sart"     in nl: return C.RED
        if "military" in nl: return C.RED
    return C.WHITE

# ─────────────────────────────────────────────
# MID → COUNTRY LOOKUP
# ─────────────────────────────────────────────
MID_TO_COUNTRY = {
    201: "Albania", 202: "Andorra", 203: "Austria", 204: "Azores",
    205: "Belgium", 206: "Belarus", 207: "Bulgaria", 208: "Vatican City",
    209: "Cyprus", 210: "Cyprus", 211: "Germany", 212: "Cyprus",
    213: "Georgia", 214: "Moldova", 215: "Malta", 216: "Armenia",
    218: "Germany", 219: "Denmark", 220: "Denmark", 224: "Spain",
    225: "Spain", 226: "France", 227: "France", 228: "France",
    229: "Malta", 230: "Finland", 231: "Faroe Islands", 232: "United Kingdom",
    233: "United Kingdom", 234: "United Kingdom", 235: "United Kingdom",
    236: "Gibraltar", 237: "Greece", 238: "Croatia", 239: "Greece",
    240: "Greece", 241: "Greece", 242: "Morocco", 243: "Hungary",
    244: "Netherlands", 245: "Netherlands", 246: "Netherlands",
    247: "Italy", 248: "Malta", 249: "Malta", 250: "Ireland",
    251: "Iceland", 252: "Liechtenstein", 253: "Luxembourg", 254: "Monaco",
    255: "Madeira", 256: "Malta", 257: "Norway", 258: "Norway",
    259: "Norway", 261: "Poland", 262: "Montenegro", 263: "Portugal",
    264: "Romania", 265: "Sweden", 266: "Sweden", 267: "Slovak Republic",
    268: "San Marino", 269: "Switzerland", 270: "Czech Republic",
    271: "Turkey", 272: "Ukraine", 273: "Russia", 274: "N. Macedonia",
    275: "Latvia", 276: "Estonia", 277: "Lithuania", 278: "Slovenia",
    279: "Serbia", 301: "Anguilla", 303: "Alaska (USA)",
    304: "Antigua & Barbuda", 305: "Antigua & Barbuda",
    306: "Sint Maarten/Bonaire", 307: "Aruba", 308: "Bahamas",
    309: "Bahamas", 310: "Bermuda", 311: "Bahamas", 312: "Belize",
    314: "Barbados", 316: "Canada", 317: "Canada", 319: "Cayman Islands",
    321: "Costa Rica", 323: "Cuba", 325: "Dominica",
    327: "Dominican Republic", 329: "Guadeloupe", 330: "Grenada",
    331: "Greenland", 332: "Guatemala", 334: "Honduras", 336: "Haiti",
    338: "United States", 339: "Jamaica", 341: "St Kitts & Nevis",
    343: "St Lucia", 345: "Mexico", 347: "Martinique", 348: "Montserrat",
    350: "Nicaragua", 351: "Panama", 352: "Panama", 353: "Panama",
    354: "Panama", 355: "Panama", 356: "Panama", 357: "Panama",
    358: "Puerto Rico", 359: "El Salvador", 361: "St Pierre & Miquelon",
    362: "Trinidad & Tobago", 364: "Turks & Caicos",
    366: "United States", 367: "United States", 368: "United States",
    369: "United States", 370: "Panama", 371: "Panama", 372: "Panama",
    373: "Panama", 374: "Panama", 375: "St Vincent & Gren.",
    376: "St Vincent & Gren.", 377: "St Vincent & Gren.",
    378: "British Virgin Is.", 379: "US Virgin Islands",
    401: "Afghanistan", 403: "Saudi Arabia", 405: "Bangladesh",
    408: "Bahrain", 410: "Bhutan", 412: "China", 413: "China",
    414: "China", 416: "Taiwan", 417: "Sri Lanka", 419: "India",
    422: "Iran", 423: "Azerbaijan", 425: "Iraq", 428: "Israel",
    431: "Japan", 432: "Japan", 434: "Turkmenistan", 436: "Kazakhstan",
    437: "Uzbekistan", 438: "Jordan", 440: "South Korea",
    441: "South Korea", 443: "Palestine", 445: "North Korea",
    447: "Kuwait", 450: "Lebanon", 451: "Kyrgyzstan", 453: "Macao",
    455: "Maldives", 457: "Mongolia", 459: "Nepal", 461: "Oman",
    463: "Pakistan", 466: "Qatar", 468: "Syria", 470: "UAE",
    471: "UAE", 472: "Tajikistan", 473: "Yemen", 477: "Hong Kong",
    478: "Bosnia & Herz.", 501: "Antarctica", 503: "Australia",
    506: "Myanmar", 508: "Brunei", 510: "Micronesia", 511: "Palau",
    512: "New Zealand", 514: "Cambodia", 515: "Cambodia",
    516: "Christmas Island", 518: "Cook Islands", 520: "Fiji",
    523: "Cocos Islands", 525: "Indonesia", 529: "Kiribati",
    531: "Laos", 533: "Malaysia", 536: "N. Mariana Islands",
    538: "Marshall Islands", 540: "New Caledonia", 542: "Niue",
    544: "Nauru", 546: "French Polynesia", 548: "Philippines",
    550: "East Timor", 553: "Papua New Guinea", 555: "Pitcairn Islands",
    557: "Solomon Islands", 559: "American Samoa", 561: "Samoa",
    563: "Singapore", 564: "Singapore", 565: "Singapore",
    566: "Singapore", 567: "Thailand", 570: "Tonga", 572: "Tuvalu",
    574: "Vietnam", 576: "Vanuatu", 577: "Vanuatu",
    578: "Wallis & Futuna", 601: "South Africa", 603: "Angola",
    605: "Algeria", 610: "Benin", 611: "Botswana",
    612: "Central African Rep.", 613: "Cameroon", 615: "Congo",
    616: "Comoros", 617: "Cabo Verde", 619: "Ivory Coast",
    620: "Comoros", 621: "Djibouti", 622: "Egypt", 624: "Ethiopia",
    625: "Eritrea", 626: "Gabon", 627: "Ghana", 629: "Gambia",
    630: "Guinea-Bissau", 631: "Eq. Guinea", 632: "Guinea",
    633: "Burkina Faso", 634: "Kenya", 636: "Liberia", 637: "Liberia",
    638: "South Sudan", 642: "Libya", 644: "Lesotho", 645: "Mauritius",
    647: "Madagascar", 649: "Mali", 650: "Mozambique",
    654: "Mauritania", 655: "Malawi", 656: "Niger", 657: "Nigeria",
    659: "Namibia", 660: "Reunion", 661: "Rwanda", 662: "Sudan",
    663: "Senegal", 664: "Seychelles", 665: "St Helena",
    666: "Somalia", 667: "Sierra Leone", 668: "Sao Tome & Principe",
    669: "Swaziland", 670: "Chad", 671: "Togo", 672: "Tunisia",
    674: "Tanzania", 675: "Uganda", 676: "DR Congo", 677: "Tanzania",
    678: "Zambia", 679: "Zimbabwe", 701: "Argentina", 710: "Brazil",
    720: "Bolivia", 725: "Chile", 730: "Colombia", 735: "Ecuador",
    740: "Falkland Islands", 745: "French Guiana", 750: "Guyana",
    755: "Paraguay", 760: "Peru", 765: "Suriname", 770: "Uruguay",
    775: "Venezuela",
}

NAV_STATUS = {
    0:  "Underway (engine)", 1:  "At anchor",
    2:  "Not under command", 3:  "Restricted manoeuvr.",
    4:  "Constrained/draught", 5:  "Moored",
    6:  "Aground",            7:  "Fishing",
    8:  "Underway (sailing)", 14: "SART/MOB/EPIRB",
    15: "—",
}

def decode_vessel_type(code):
    if code is None: return "—"
    code = int(code)
    if code == 0:        return "—"
    if code == 30:       return "Fishing"
    if code == 31:       return "Towing"
    if code == 32:       return "Towing (large)"
    if code == 33:       return "Dredging"
    if code == 34:       return "Diving ops"
    if code == 35:       return "Military"
    if code == 36:       return "Sailing"
    if code == 37:       return "Pleasure craft"
    if 40 <= code < 50:  return "High-speed craft"
    if code == 50:       return "Pilot vessel"
    if code == 51:       return "Search & Rescue"
    if code == 52:       return "Tug"
    if code == 53:       return "Port tender"
    if code == 55:       return "Law enforcement"
    if code == 58:       return "Medical"
    if 60 <= code < 70:  return "Passenger"
    if 70 <= code < 80:  return "Cargo"
    if 80 <= code < 90:  return "Tanker"
    if 90 <= code < 100: return "Other"
    return "—"

def decode_mmsi(mmsi):
    s = str(mmsi).zfill(9)
    if s.startswith("111"):
        return MID_TO_COUNTRY.get(int(s[3:6]), "?"), "SAR Aircraft"
    if s.startswith("99"):
        return MID_TO_COUNTRY.get(int(s[2:5]), "?"), "AtoN"
    if s.startswith("00"):
        return MID_TO_COUNTRY.get(int(s[2:5]), "?"), "Coast Station"
    mid = int(s[0:3])
    return MID_TO_COUNTRY.get(mid, f"MID:{mid}"), "Vessel"

# ─────────────────────────────────────────────
# VESSEL CACHE
# ─────────────────────────────────────────────
vessel_cache = {}  # mmsi → dict
update_order = []  # MMSIs ordered by last update, most recent last

def upsert(mmsi, updates):
    if mmsi not in vessel_cache:
        vessel_cache[mmsi] = {
            "name": "UNKNOWN", "mmsi": mmsi,
            "country": "—", "vtype": "—", "dest": "—",
            "lat": None, "lon": None,
            "sog": "—", "hdg": "—", "nav": "—",
            "length": "—", "callsign": "—", "imo": "—",
            "draught": "—", "eta": "—",
            "last_seen": time.time(), "msg_count": 0,
        }
    vessel_cache[mmsi].update(updates)
    vessel_cache[mmsi]["last_seen"] = time.time()
    vessel_cache[mmsi]["msg_count"] += 1
    if mmsi in update_order:
        update_order.remove(mmsi)
    update_order.append(mmsi)

# ─────────────────────────────────────────────
# TERMINAL DISPLAY
# ─────────────────────────────────────────────
COLS = {
    "name":  20,
    "flag":  18,
    "type":  14,
    "dest":  14,
    "lat":    8,
    "lon":    8,
    "sog":    5,
    "hdg":   11,
    "nav":   20,
    "age":    4,
    "cnt":    4,
}

# render_table owns exactly TABLE_SIZE + 2 lines (rows + blank + footer)
_RENDER_LINES = TABLE_SIZE + 2

def trunc(s, n):
    s = str(s)
    return s[:n] if len(s) > n else s

def print_header():
    """Printed once at startup — never redrawn."""
    h = (
        f"  {'Name':<{COLS['name']}} "
        f"{'Flag':<{COLS['flag']}} "
        f"{'Type':<{COLS['type']}} "
        f"{'Destination':<{COLS['dest']}} "
        f"{'Lat':>{COLS['lat']}} "
        f"{'Lon':>{COLS['lon']}}  "
        f"{'SOG':>{COLS['sog']}}  "
        f"{'HDG':<{COLS['hdg']}} "
        f"{'Nav Status':<{COLS['nav']}} "
        f"{'Age':>{COLS['age']}} "
        f"{'#':>{COLS['cnt']}}"
    )
    sys.stdout.write(C.BOLD + h + C.RESET + "\n")
    sys.stdout.write("  " + "─" * 128 + "\n")
    sys.stdout.flush()

def render_table():
    rows_to_show = update_order[-TABLE_SIZE:][::-1]

    lines = []
    now = time.time()
    for mmsi in rows_to_show:
        v    = vessel_cache[mmsi]
        age  = int(now - v["last_seen"])
        lat  = f"{v['lat']:.4f}"  if v["lat"] is not None else "—"
        lon  = f"{v['lon']:.4f}"  if v["lon"] is not None else "—"
        col  = vessel_color(v["vtype"], v["nav"])

        # Dim rows that haven't updated in >60s
        prefix = C.DIM if age > 60 else col

        line = (
            f"{prefix}"
            f"  {trunc(v['name'],    COLS['name']):<{COLS['name']}} "
            f"{trunc(v['country'],   COLS['flag']):<{COLS['flag']}} "
            f"{trunc(v['vtype'],     COLS['type']):<{COLS['type']}} "
            f"{trunc(v['dest'],      COLS['dest']):<{COLS['dest']}} "
            f"{lat:>{COLS['lat']}} "
            f"{lon:>{COLS['lon']}}  "
            f"{str(v['sog']):>{COLS['sog']}}  "
            f"{trunc(v['hdg'],       COLS['hdg']):<{COLS['hdg']}} "
            f"{trunc(v['nav'],       COLS['nav']):<{COLS['nav']}} "
            f"{age:>{COLS['age']}} "
            f"{v['msg_count']:>{COLS['cnt']}}"
            f"{C.RESET}"
        )
        lines.append(line)

    # Pad to fixed TABLE_SIZE rows
    while len(lines) < TABLE_SIZE:
        lines.append("")

    # Footer (blank line + stats)
    elapsed = time.time() - start_time if start_time else 0
    lines.append("")
    lines.append(
        f"{C.DIM}  Region: {region_label}  │  "
        f"Vessels: {len(vessel_cache)}  │  "
        f"Msgs: {msg_count}  │  "
        f"Static: {static_count}  │  "
        f"Uptime: {int(elapsed)}s  │  "
        f"Ctrl+C to stop{C.RESET}"
    )

    if hasattr(render_table, "initialized"):
        sys.stdout.write(f"\033[{_RENDER_LINES}A")
    else:
        render_table.initialized = True

    for line in lines:
        sys.stdout.write("\033[2K" + line + "\n")
    sys.stdout.flush()

# ─────────────────────────────────────────────
# COUNTERS / STATE
# ─────────────────────────────────────────────
msg_count       = 0
static_count    = 0   # counts ShipStaticData messages received
start_time      = None
LAT_MIN = LAT_MAX = LON_MIN = LON_MAX = None
region_label = ""

def in_box(lat, lon):
    return LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX

# ─────────────────────────────────────────────
# WEBSOCKET CALLBACKS
# ─────────────────────────────────────────────

def on_open(ws):
    global start_time
    start_time = time.time()
    print("\n" + "=" * 60)
    print("✅  WebSocket CONNECTED")
    print("=" * 60)
    if API_KEY == "YOUR_API_KEY_HERE":
        print("\n🚨  ERROR: You have not set your API key!")
        ws.close()
        return
    sub_msg = {
        "APIKey": API_KEY,
        "BoundingBoxes": [[[LAT_MIN, LON_MIN], [LAT_MAX, LON_MAX]]],
    }
    ws.send(json.dumps(sub_msg))
    print(f"🌍  Region   : {region_label}")
    print(f"📦  BBox     : [{LAT_MIN},{LON_MIN}] → [{LAT_MAX},{LON_MAX}]")
    print(f"📋  Showing  : top {TABLE_SIZE} most recently updated vessels\n")
    print_header()


def on_message(ws, message):
    global msg_count, static_count

    msg_count += 1
    if isinstance(message, bytes):
        message = message.decode("utf-8")

    try:
        data = json.loads(message)
    except Exception:
        return

    mtype = data.get("MessageType", "UNKNOWN")

    if "Error" in data or mtype == "ERROR":
        sys.stdout.write(f"\033[{_RENDER_LINES + 3}B")
        print(f"🚨  SERVER ERROR: {data}")
        return

    if mtype not in {
        "PositionReport", "StandardClassBPositionReport",
        "ExtendedClassBPositionReport", "ShipStaticData",
    }:
        return

    meta = data.get("MetaData", {})
    lat  = meta.get("latitude")  or meta.get("Latitude")
    lon  = meta.get("longitude") or meta.get("Longitude")
    if lat is None or lon is None:
        return
    if not in_box(lat, lon):
        return

    mmsi    = meta.get("MMSI", 0)
    name    = (meta.get("ShipName") or "").strip() or None
    country, _ = decode_mmsi(mmsi)

    msg_body = data.get("Message", {}).get(mtype, {})

    # Motion fields (PositionReport / ClassB)
    sog = msg_body.get("Sog")
    hdg = msg_body.get("TrueHeading")
    cog = msg_body.get("Cog")
    nav = msg_body.get("NavigationalStatus")

    sog_str = f"{sog:.1f}" if isinstance(sog, (int, float)) else None
    if isinstance(hdg, (int, float)) and hdg != 511:
        hdg_str = f"{hdg:.0f}°"
    elif isinstance(cog, (int, float)):
        hdg_str = f"{cog:.1f}°(C)"
    else:
        hdg_str = None
    nav_str = NAV_STATUS.get(nav, None) if nav is not None else None

    # Static fields (ShipStaticData only)
    # AISStream uses 'Type' not 'TypeOfShipAndCargoType'
    vtype_str = None
    length_str = None
    callsign_str = None
    imo_str = None
    draught_str = None
    eta_str = None
    if mtype == "ShipStaticData":
        static_count += 1
        vtype_code = msg_body.get("Type")
        if vtype_code is not None:
            decoded = decode_vessel_type(int(vtype_code))
            if decoded != "—":
                vtype_str = decoded
        # Ship dimensions → overall length = A + B
        dim = msg_body.get("Dimension")
        if isinstance(dim, dict):
            length = (dim.get("A") or 0) + (dim.get("B") or 0)
            beam   = (dim.get("C") or 0) + (dim.get("D") or 0)
            if length > 0:
                length_str = f"{length}x{beam}m"
        callsign = (msg_body.get("CallSign") or "").strip()
        if callsign:
            callsign_str = callsign
        imo = msg_body.get("ImoNumber")
        if imo and int(imo) > 0:
            imo_str = str(imo)
        draught = msg_body.get("MaximumStaticDraught")
        if draught and float(draught) > 0:
            draught_str = f"{draught}m"
        eta = msg_body.get("Eta")
        if isinstance(eta, dict):
            mo = eta.get("Month", 0)
            dy = eta.get("Day", 0)
            hr = eta.get("Hour", 0)
            mn = eta.get("Minute", 0)
            if mo > 0 and dy > 0:
                eta_str = f"{mo:02d}/{dy:02d} {hr:02d}:{mn:02d}"

    # Destination — AIS pads unused fields with @ signs up to 20 chars
    dest_raw = (msg_body.get("Destination") or "").strip().rstrip("@").strip()
    dest_str = dest_raw if dest_raw and dest_raw.upper() not in ("", "NONE") else None

    # Build update — only overwrite fields we actually received
    updates = {"lat": lat, "lon": lon, "country": country}
    if name:            updates["name"]     = name
    if sog_str:         updates["sog"]      = sog_str
    if hdg_str:         updates["hdg"]      = hdg_str
    if nav_str and nav_str != "—": updates["nav"] = nav_str
    if vtype_str:       updates["vtype"]    = vtype_str
    if dest_str:        updates["dest"]     = dest_str
    if length_str:      updates["length"]   = length_str
    if callsign_str:    updates["callsign"] = callsign_str
    if imo_str:         updates["imo"]      = imo_str
    if draught_str:     updates["draught"]  = draught_str
    if eta_str:         updates["eta"]      = eta_str

    upsert(mmsi, updates)
    render_table()


def on_error(ws, error):
    elapsed = time.time() - start_time if start_time else 0
    print(f"\n🚨  ERROR (t={elapsed:.1f}s): {error}")
    if "401" in str(error) or "403" in str(error):
        print("    ➜ Invalid or missing API key.")


def on_close(ws, close_status_code, close_msg):
    elapsed = time.time() - start_time if start_time else 0
    print(f"\n{'=' * 60}")
    print(f"🔌  CLOSED  status:{close_status_code}  uptime:{int(elapsed)}s")
    print(f"    Vessels tracked : {len(vessel_cache)}")
    print(f"    Total messages  : {msg_count}")
    if close_status_code == 1006:
        print("⚠️  Code 1006 = abnormal closure (key, idle timeout, or server drop).")
    print("=" * 60)


# ─────────────────────────────────────────────
# ARGUMENT PARSING
# ─────────────────────────────────────────────
def parse_args():
    global LAT_MIN, LAT_MAX, LON_MIN, LON_MAX, region_label
    global TABLE_SIZE, _RENDER_LINES

    parser = argparse.ArgumentParser(
        description="AISStream live vessel tracker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(
            f"  {k:<12} {v[4]}" for k, v in REGIONS.items()
        )
    )
    parser.add_argument(
        "--region", "-r",
        default="channel",
        choices=list(REGIONS.keys()) + ["custom"],
        help="Predefined region (default: channel)"
    )
    parser.add_argument(
        "--bbox",
        help='Custom bounding box: "LAT_MIN LAT_MAX LON_MIN LON_MAX" (use with --region custom)',
        metavar="BBOX"
    )
    parser.add_argument(
        "--table", "-t",
        type=int,
        default=TABLE_SIZE,
        help=f"Number of rows to display (default: {TABLE_SIZE})"
    )
    args = parser.parse_args()

    TABLE_SIZE    = args.table
    _RENDER_LINES = TABLE_SIZE + 2

    if args.region == "custom":
        if not args.bbox:
            parser.error("--region custom requires --bbox 'LAT_MIN LAT_MAX LON_MIN LON_MAX'")
        try:
            parts = [float(x) for x in args.bbox.split()]
            LAT_MIN, LAT_MAX, LON_MIN, LON_MAX = parts
            region_label = f"Custom [{LAT_MIN},{LON_MIN}]→[{LAT_MAX},{LON_MAX}]"
        except Exception:
            parser.error("--bbox must be four numbers e.g. '50.5 51.5 1.0 2.5'")
    else:
        LAT_MIN, LAT_MAX, LON_MIN, LON_MAX, region_label = REGIONS[args.region]

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    parse_args()

    print(f"\n{C.BOLD}AISStream Vessel Tracker{C.RESET} — Python {sys.version.split()[0]}")
    print(f"Connecting to wss://stream.aisstream.io/v0/stream ...")

    # Color legend
    print(
        f"\nColor key:  "
        f"{C.YELLOW}■ Tanker{C.RESET}  "
        f"{C.WHITE}■ Cargo{C.RESET}  "
        f"{C.CYAN}■ Passenger/HSC{C.RESET}  "
        f"{C.ORANGE}■ Tug/Towing{C.RESET}  "
        f"{C.GREEN}■ Fishing{C.RESET}  "
        f"{C.MAGENTA}■ Sailing/Pleasure{C.RESET}  "
        f"{C.RED}■ SAR/Military{C.RESET}  "
        f"{C.BLUE}■ Pilot{C.RESET}  "
        f"{C.GREY}■ Unknown{C.RESET}  "
        f"{C.DIM}■ Stale >60s{C.RESET}"
    )

    ws = websocket.WebSocketApp(
        "wss://stream.aisstream.io/v0/stream",
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )

    try:
        ws.run_forever(ping_interval=30, ping_timeout=10, reconnect=5)
    except KeyboardInterrupt:
        print(f"\n⏹️  Stopped. {len(vessel_cache)} vessels tracked, {msg_count} messages.")
