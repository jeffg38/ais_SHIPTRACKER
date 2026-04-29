# code.py — AIS Ship Tracker Display
# Matrix Portal S3 + 64x64 RGB LED Matrix (Adafruit #5362)
#
# REQUIRED LIBRARIES in /lib on CIRCUITPY:
#   - adafruit_display_text (folder)
#   - adafruit_connection_manager.mpy
#   - adafruit_requests.mpy
#
# All from the Adafruit CircuitPython Bundle:
#   https://circuitpython.org/libraries
#
# settings.toml must contain:
#   CIRCUITPY_WIFI_SSID = "your_wifi_name"
#   CIRCUITPY_WIFI_PASSWORD = "your_wifi_password"
#   AIS_SERVER_IP = "192.168.0.51"
#   AIS_SERVER_PORT = "5000"
#
# DISPLAY LAYOUT (64x64):
#   Rows  0-54 : Map area — coastline + vessel dots
#   Row  55    : Divider line
#   Rows 56-63 : Scrolling ticker

import board
import digitalio
import displayio
import framebufferio
import rgbmatrix
import terminalio
import time
import wifi
import socketpool
import ssl
import os
import gc
import math

import adafruit_requests
from adafruit_display_text import label

# ─────────────────────────────────────────────
# DISPLAY CONSTANTS
# ─────────────────────────────────────────────
DISPLAY_W  = 64
DISPLAY_H  = 64
MAP_H      = 55      # rows 0-54 = map area
DIVIDER_Y  = 55      # 1px divider line
TICKER_Y   = 56      # rows 56-63 = ticker

# ─────────────────────────────────────────────
# BOUNDING BOX — English Channel
# ─────────────────────────────────────────────
LAT_MIN = 50.5
LAT_MAX = 51.5
LON_MIN = 1.0
LON_MAX = 2.5

# ─────────────────────────────────────────────
# PALETTE INDICES (fixed)
# ─────────────────────────────────────────────
P_BG      = 0    # black background
P_LAND    = 1    # dark green land fill
P_COAST   = 2    # bright green coast edge
P_DIV     = 3    # divider line
P_UNKNOWN = 4    # grey — type unknown
P_STALE   = 5    # very dim — stale vessel
P_HDG     = 6    # heading indicator pixel
# Vessel type colors start at index 7
P_TANKER  = 7
P_CARGO   = 8
P_PASS    = 9
P_TUG     = 10
P_FISH    = 11
P_SAIL    = 12
P_SAR     = 13
P_PILOT   = 14
P_HSC     = 15
P_OTHER   = 16
P_CITY    = 17   # warm white for city markers
PALETTE_SIZE = 18

# ─────────────────────────────────────────────
# VESSEL TYPE → PALETTE INDEX
# ─────────────────────────────────────────────
def type_to_palette(vtype):
    if not vtype or vtype in ("—", "\u2014", "?", ""):
        return P_UNKNOWN
    vt = vtype.lower()
    if "tanker"    in vt: return P_TANKER
    if "cargo"     in vt: return P_CARGO
    if "passenger" in vt: return P_PASS
    if "tug"       in vt: return P_TUG
    if "towing"    in vt: return P_TUG
    if "fishing"   in vt: return P_FISH
    if "sailing"   in vt: return P_SAIL
    if "pleasure"  in vt: return P_SAIL
    if "search"    in vt: return P_SAR
    if "militar"   in vt: return P_SAR
    if "law"       in vt: return P_SAR
    if "pilot"     in vt: return P_PILOT
    if "high-speed" in vt: return P_HSC
    if "high speed" in vt: return P_HSC
    return P_OTHER


# ─────────────────────────────────────────────
# COORDINATE → PIXEL
# ─────────────────────────────────────────────
def to_pixel(lat, lon):
    x = int((lon - LON_MIN) / (LON_MAX - LON_MIN) * (DISPLAY_W - 1))
    y = int((LAT_MAX - lat) / (LAT_MAX - LAT_MIN) * (MAP_H - 1))
    return max(0, min(DISPLAY_W-1, x)), max(0, min(MAP_H-1, y))


# ─────────────────────────────────────────────
# COASTLINE — English Channel 64x55
# UK: Kent coast with Thanet headland knob
# FR: Belgian/French coast rising L→R (Boulogne low, Dunkirk high)
# Uses bytearray for memory efficiency (3.5KB vs ~60KB for a set)
# ─────────────────────────────────────────────
def _build_land():
    bmp = bytearray(DISPLAY_W * MAP_H)

    # UK / Kent coast — Thanet headland then tapering SW to Folkestone
    for row, width in (
        (0,28),(1,30),(2,32),(3,30),(4,28),
        (5,24),(6,20),(7,16),(8,13),(9,10),
        (10,8),(11,6),(12,4),(13,3),
    ):
        for x in range(width):
            bmp[row * DISPLAY_W + x] = 1

    # French/Belgian coast — per-column top edge, rises L→R
    # Boulogne(low/south) → Calais → Dunkirk(high/north)
    FR_TOP = [
        47,47,47,47,47,47,47,   # x 0-6   Boulogne (7)
        44,44,44,44,            # x 7-10  Cap Gris Nez (4)
        45,45,45,45,45,         # x 11-15 (5)
        45,45,45,45,45,         # x 16-20 (5)
        46,46,46,46,46,46,46,46,# x 21-28 Wissant (8)
        44,44,44,44,44,44,44,   # x 29-35 Calais (7)
        43,43,43,43,43,43,43,   # x 36-42 Gravelines (7)
        42,42,42,42,42,42,42,42,# x 43-50 (8)
        41,41,41,41,41,41,41,   # x 51-57 (7)
        40,40,40,40,40,40,       # x 58-63 Dunkirk (6)
    ]
    for x, top in enumerate(FR_TOP):
        for y in range(top, MAP_H):
            bmp[y * DISPLAY_W + x] = 1

    return bmp

LAND_BMP = _build_land()

def _is_land(x, y):
    if x < 0 or x >= DISPLAY_W or y < 0 or y >= MAP_H:
        return False
    return LAND_BMP[y * DISPLAY_W + x] == 1

# Build LAND_PIXELS and LAND_SET from bytearray for compatibility
# with existing draw/ticker code — but keep them small
LAND_PIXELS = [
    (x, y) for y in range(MAP_H)
    for x in range(DISPLAY_W)
    if LAND_BMP[y * DISPLAY_W + x] == 1
]
LAND_SET = set(LAND_PIXELS)


# ─────────────────────────────────────────────
# MATRIX + DISPLAY SETUP
# ─────────────────────────────────────────────
displayio.release_displays()

matrix = rgbmatrix.RGBMatrix(
    width=DISPLAY_W, height=DISPLAY_H, bit_depth=2,
    rgb_pins=[
        board.MTX_R1, board.MTX_G1, board.MTX_B1,
        board.MTX_R2, board.MTX_G2, board.MTX_B2,
    ],
    addr_pins=[
        board.MTX_ADDRA, board.MTX_ADDRB, board.MTX_ADDRC,
        board.MTX_ADDRD, board.MTX_ADDRE,
    ],
    clock_pin=board.MTX_CLK,
    latch_pin=board.MTX_LAT,
    output_enable_pin=board.MTX_OE,
)

display = framebufferio.FramebufferDisplay(matrix, auto_refresh=False)

# ─────────────────────────────────────────────
# PALETTE
# ─────────────────────────────────────────────
palette = displayio.Palette(PALETTE_SIZE)
palette[P_BG]      = 0x000000
palette[P_LAND]    = 0x145014
palette[P_COAST]   = 0x28A028
palette[P_DIV]     = 0x143C14
palette[P_UNKNOWN] = 0x646464
palette[P_STALE]   = 0x282828
palette[P_HDG]     = 0x383838
palette[P_TANKER]  = 0xFFC800
palette[P_CARGO]   = 0xFF7800
palette[P_PASS]    = 0x00DCDC
palette[P_TUG]     = 0xFF8C00
palette[P_FISH]    = 0x00C800
palette[P_SAIL]    = 0xC800C8
palette[P_SAR]     = 0xFF3232
palette[P_PILOT]   = 0x0064FF
palette[P_HSC]     = 0x00C8DC
palette[P_OTHER]   = 0x969696
palette[P_CITY]    = 0xFFFFCC   # warm white for city markers

# ─────────────────────────────────────────────
# BITMAP + TILE GRID
# ─────────────────────────────────────────────
bitmap    = displayio.Bitmap(DISPLAY_W, DISPLAY_H, PALETTE_SIZE)
tile_grid = displayio.TileGrid(bitmap, pixel_shader=palette)

# Ticker label
ticker_label = label.Label(
    terminalio.FONT,
    color=0x00CC44,
    text="  Connecting...  ",
)
ticker_label.x = DISPLAY_W
ticker_label.y = TICKER_Y + 4

root_group = displayio.Group()
root_group.append(tile_grid)
root_group.append(ticker_label)
display.root_group = root_group


# ─────────────────────────────────────────────
# DRAW HELPERS
# ─────────────────────────────────────────────
def draw_static():
    """Clear display and draw land + divider. Call before drawing vessels."""
    # Clear to background
    for y in range(DISPLAY_H):
        for x in range(DISPLAY_W):
            bitmap[x, y] = P_BG

    # Land and coast edge
    for (lx, ly) in LAND_PIXELS:
        edge = False
        for dx, dy in ((-1,0),(1,0),(0,-1),(0,1)):
            nx, ny = lx+dx, ly+dy
            if nx<0 or nx>=DISPLAY_W or ny<0 or ny>=MAP_H or (nx,ny) not in LAND_SET:
                edge = True
                break
        bitmap[lx, ly] = P_COAST if edge else P_LAND

    # Divider
    for x in range(DISPLAY_W):
        bitmap[x, DIVIDER_Y] = P_DIV

    # City markers — warm white plus shape, hardcoded coast edge pixels
    for (cx, cy) in (
        ( 7, 10),   # Folkestone
        (12,  8),   # Dover
        (27,  4),   # Ramsgate
        ( 8, 44),   # Boulogne
        (33, 44),   # Calais
        (58, 40),   # Dunkirk
    ):
        for dx, dy in ((0,0),(1,0),(-1,0),(0,1),(0,-1)):
            nx, ny = cx+dx, cy+dy
            if 0 <= nx < DISPLAY_W and 0 <= ny < MAP_H:
                bitmap[nx, ny] = P_CITY


def draw_vessels(vessels):
    """Redraw map area with current vessel positions."""
    draw_static()
    for v in vessels:
        try:
            lat   = float(v["lat"])
            lon   = float(v["lon"])
            age_s = int(v.get("age", 0))
        except (ValueError, TypeError):
            continue

        px, py = to_pixel(lat, lon)
        if (px, py) in LAND_SET:
            continue

        pidx = P_STALE if age_s > 300 else type_to_palette(v.get("type", ""))
        bitmap[px, py] = pidx

        # Heading indicator
        if age_s <= 300:
            try:
                sog = float(str(v.get("sog","0")).strip())
                hdg_s = str(v.get("hdg","")).replace("\u00b0","").replace("(C)","").strip()
                hdg = float(hdg_s)
                if sog > 0.5:
                    rad = (hdg - 90) * math.pi / 180
                    hx = px + round(math.cos(rad) * 1.5)
                    hy = py + round(math.sin(rad) * 1.5)
                    if (0 <= hx < DISPLAY_W and 0 <= hy < MAP_H
                            and (hx, hy) not in LAND_SET
                            and bitmap[hx, hy] == P_BG):
                        bitmap[hx, hy] = P_HDG
            except (ValueError, TypeError):
                pass


def build_ticker(vessels):
    """
    Build scrolling ticker string — capped at 20 vessels.
    Returns (text, offsets) where offsets is a list of
    (pixel_offset, px, py, palette_idx, entry_width).
    pixel_offset is the x position in pixels where the entry starts
    in the final joined string — accounts for 3-space separators.
    """
    parts = []
    offsets = []
    count = 0
    SEP = "   "           # separator between entries — must match join below
    SEP_W = len(SEP) * 6  # separator width in pixels

    for v in vessels:
        if count >= 20:
            break
        age_s = int(v.get("age", 0))
        if age_s > 300:
            continue

        name = v.get("name", "?")[:20]
        dest = v.get("dest", "?")
        sog  = str(v.get("sog", "?")).strip()
        hdg  = str(v.get("hdg", "?")).replace("\u00b0","").replace("(C)","").strip()

        if dest in ("—", "\u2014", ""): dest = "?"
        if sog  in ("—", "\u2014", ""): sog  = "?"
        if hdg  in ("—", "\u2014", ""): hdg  = "?"
        if sog != "?" and "kn" not in sog:
            sog = sog + "kn"

        # 2-char vessel type code prefix
        vt = (v.get("type") or "").lower()
        if   "tanker"     in vt: code = "TK"
        elif "cargo"      in vt: code = "CG"
        elif "passenger"  in vt: code = "PS"
        elif "tug"        in vt: code = "TG"
        elif "towing"     in vt: code = "TG"
        elif "fishing"    in vt: code = "FV"
        elif "sailing"    in vt: code = "SV"
        elif "pleasure"   in vt: code = "SV"
        elif "search"     in vt: code = "SR"
        elif "militar"    in vt: code = "ML"
        elif "pilot"      in vt: code = "PV"
        elif "high-speed" in vt: code = "HS"
        elif "high speed" in vt: code = "HS"
        else:                    code = "??"

        # Short nav status — only shown when notable (not underway)
        nav = (v.get("nav") or "").lower()
        if   "anchor"     in nav: nav_code = " ANCH"
        elif "moored"     in nav: nav_code = " MOOR"
        elif "restricted" in nav: nav_code = " RESTR"
        elif "constrained" in nav: nav_code = " DRGHT"
        elif "aground"    in nav: nav_code = " AGRND"
        elif "fishing"    in nav: nav_code = " FISH"
        elif "sart"       in nav: nav_code = " EMRG"
        elif "sailing"    in nav: nav_code = " SAIL"
        else:                     nav_code = ""

        entry = f"{code} {name}>{dest} {sog} {hdg}{nav_code}"
        parts.append(entry)

        # Calculate pixel offset of this entry in the final string.
        # The final string is: entry0 + SEP + entry1 + SEP + entry2 ...
        # So offset of entry N = sum of (len(entry_i) + len(SEP)) for i < N
        pixel_offset = sum((len(p) + len(SEP)) * 6 for p in parts[:-1])
        entry_width  = len(entry) * 6

        try:
            lat = float(v["lat"])
            lon = float(v["lon"])
            px, py = to_pixel(lat, lon)
            if (px, py) not in LAND_SET:
                pidx = type_to_palette(v.get("type", ""))
                offsets.append((pixel_offset, px, py, pidx, entry_width))
        except (ValueError, TypeError):
            pass

        count += 1

    text = SEP.join(parts) if parts else "No vessels"
    return text, offsets


# ─────────────────────────────────────────────
# WIFI CONNECTION
# ─────────────────────────────────────────────
print("Connecting to WiFi...")
draw_static()
wifi_label = label.Label(terminalio.FONT, color=0xFFAA00, text="WiFi...")
wifi_label.x = 2
wifi_label.y = 28
root_group.append(wifi_label)
display.refresh(minimum_frames_per_second=0)

try:
    wifi.radio.connect(
        os.getenv("CIRCUITPY_WIFI_SSID"),
        os.getenv("CIRCUITPY_WIFI_PASSWORD"),
    )
    print(f"WiFi connected: {wifi.radio.ipv4_address}")
    root_group.remove(wifi_label)
except Exception as e:
    print(f"WiFi error: {e}")
    wifi_label.text = "WiFi FAIL"
    wifi_label.color = 0xFF0000
    display.refresh(minimum_frames_per_second=0)
    while True:
        time.sleep(1)

pool    = socketpool.SocketPool(wifi.radio)
session = adafruit_requests.Session(pool, ssl.create_default_context())

server_ip   = os.getenv("AIS_SERVER_IP",   "192.168.0.51")
server_port = os.getenv("AIS_SERVER_PORT", "5000")
DATA_URL    = f"http://{server_ip}:{server_port}/vessels.json"
print(f"Polling: {DATA_URL}")

# ─────────────────────────────────────────────
# BUTTON SETUP
# ─────────────────────────────────────────────
btn_up   = digitalio.DigitalInOut(board.BUTTON_UP)
btn_down = digitalio.DigitalInOut(board.BUTTON_DOWN)
btn_up.switch_to_input(pull=digitalio.Pull.UP)
btn_down.switch_to_input(pull=digitalio.Pull.UP)

# Debounce state
up_last   = True    # True = not pressed (pull-up logic)
down_last = True

def btn_pressed(btn, last):
    """Return True on falling edge (button just pressed). Returns (triggered, new_state)."""
    cur = btn.value
    triggered = last and not cur   # was high, now low = just pressed
    return triggered, cur

# ─────────────────────────────────────────────
# OVERLAY SCREENS
# ─────────────────────────────────────────────
OVERLAY_DURATION = 6.0   # seconds before returning to live display

# Color key entries: (label text, hex color)
COLOR_KEY = [
    ("TANKER",    0xFFC800),
    ("CARGO",     0xFF7800),
    ("PASSENGER", 0x00DCDC),
    ("TUG/TOW",   0xFF8C00),
    ("FISHING",   0x00C800),
    ("SAILING",   0xC800C8),
    ("SAR/MIL",   0xFF3232),
    ("PILOT",     0x0064FF),
    ("HSC",       0x00C8DC),
    ("UNKNOWN",   0x646464),
]

def show_color_key():
    """Display color key overlay for OVERLAY_DURATION seconds."""
    g = displayio.Group()

    # Title — 9 chars * 6px = 54px, fits with margin
    t = label.Label(terminalio.FONT, color=0xFFFFFF, text="COLOR KEY")
    t.x = 4
    t.y = 4
    g.append(t)

    # Max 9 chars per line (9*6=54px), single column, 5px row spacing
    entries = [
        ("YEL Tankr",  0xFFC800),
        ("ORG Cargo",  0xFF7800),
        ("CYN Pass",   0x00DCDC),
        ("AMB Tug",    0xFF8C00),
        ("GRN Fish",   0x00C800),
        ("MAG Sail",   0xC800C8),
        ("RED SAR",    0xFF3232),
        ("BLU Pilot",  0x0064FF),
        ("LBL HSC",    0x00C8DC),
        ("GRY Unkn",   0x646464),
    ]

    for i, (txt, col) in enumerate(entries):
        lbl = label.Label(terminalio.FONT, color=col, text=txt)
        lbl.x = 2
        lbl.y = 13 + i * 5
        g.append(lbl)

    display.root_group = g
    display.refresh(minimum_frames_per_second=0)
    time.sleep(OVERLAY_DURATION)
    display.root_group = root_group
    display.refresh(minimum_frames_per_second=0)


def show_stats(vessel_count, total_msgs, start_time, region, fetch_err):
    """Display stats overlay for OVERLAY_DURATION seconds."""
    uptime_s = int(time.monotonic() - start_time)
    hrs  = uptime_s // 3600
    mins = (uptime_s % 3600) // 60
    secs = uptime_s % 60

    g = displayio.Group()

    # Title — 9 chars = 54px
    t = label.Label(terminalio.FONT, color=0x00FF55, text="AIS STATS")
    t.x = 4
    t.y = 4
    g.append(t)

    err_col = 0xFF3232 if fetch_err > 0 else 0x444444

    # All lines strictly <= 10 chars (10*6=60px)
    rgn = region[:5] if region else "?"     # "Engli" from "English Channel"
    lines = [
        (f"RGN {rgn}",              0x00CC44),
        (f"VSL {vessel_count}",     0x00DCDC),
        (f"MSG {total_msgs}",       0xFFCC00),
        (f"UP {hrs}h{mins}m{secs}s",0xFF7800),
        (f"ERR {fetch_err}",        err_col),
        (f"PI {server_ip[-8:]}",    0x646464),
        (f"PT {server_port}",       0x646464),
    ]

    for i, (txt, col) in enumerate(lines):
        lbl = label.Label(terminalio.FONT, color=col, text=txt[:10])
        lbl.x = 2
        lbl.y = 13 + i * 7
        g.append(lbl)

    display.root_group = g
    display.refresh(minimum_frames_per_second=0)
    time.sleep(OVERLAY_DURATION)
    display.root_group = root_group
    display.refresh(minimum_frames_per_second=0)

    display.root_group = g
    display.refresh(minimum_frames_per_second=0)
    time.sleep(OVERLAY_DURATION)
    display.root_group = root_group
    display.refresh(minimum_frames_per_second=0)


# ─────────────────────────────────────────────
# STATS TRACKING
# ─────────────────────────────────────────────
start_time  = time.monotonic()
total_msgs  = 0
last_vessel_count = 0

# ─────────────────────────────────────────────
# INITIAL DRAW
# ─────────────────────────────────────────────
draw_static()
display.refresh(minimum_frames_per_second=0)

# ─────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────
POLL_INTERVAL  = 10      # seconds between fetches
SCROLL_DELAY   = 0.02    # seconds per frame
SCROLL_PX      = 1       # pixels per frame

# Flash state — intervals in pixels scrolled, not frames,
# so flash rate stays consistent regardless of SCROLL_PX or SCROLL_DELAY
FLASH_PX_INTERVAL = 16   # pixels scrolled between flash toggles (~16px at 1px/frame = 320ms)
flash_vessel      = None  # (px, py, pidx) of vessel currently flashing
flash_end_x       = 0     # ticker_x value at which flash should stop
flash_px_count    = 0     # pixels scrolled since last toggle
flash_bright      = True  # current flash state

last_fetch     = -POLL_INTERVAL
ticker_x       = DISPLAY_W
fetch_errors   = 0
region_label   = "English Channel"
pending_ticker = None
pending_offsets = []
ticker_offsets = []      # current offsets for active ticker
fetch_due      = False
last_triggered = -1      # pixel_offset of last triggered flash (avoid repeat)

print("Running...")

while True:
    now = time.monotonic()

    # ── Button polling ───────────────────────────────────────
    up_triggered,   up_last   = btn_pressed(btn_up,   up_last)
    down_triggered, down_last = btn_pressed(btn_down, down_last)

    if up_triggered:
        show_color_key()

    if down_triggered:
        show_stats(last_vessel_count, total_msgs, start_time,
                   region_label if "region_label" in dir() else "?",
                   fetch_errors)

    # ── Mark fetch as due ────────────────────────────────────
    if now - last_fetch >= POLL_INTERVAL:
        fetch_due = True

    # ── Scroll ticker one step ───────────────────────────────
    ticker_x -= SCROLL_PX
    text_w = len(ticker_label.text) * 6

    if ticker_x < -text_w:
        # Wrap point — do fetch if due
        if fetch_due:
            try:
                r    = session.get(DATA_URL, timeout=8)
                data = r.json()
                r.close()
                vessels = data.get("vessels", [])
                last_vessel_count = len(vessels)
                total_msgs += last_vessel_count
                region_label = data.get("region", "?")
                print(f"{last_vessel_count} vessels")
                draw_vessels(vessels)
                new_text, new_offsets = build_ticker(vessels)
                pending_ticker  = new_text
                pending_offsets = new_offsets
                ticker_label.color = 0x00CC44
                last_fetch   = time.monotonic()
                fetch_errors = 0
                fetch_due    = False
                gc.collect()
            except Exception as e:
                print(f"Fetch error: {e}")
                fetch_errors += 1
                last_fetch = time.monotonic()
                fetch_due  = False
                if fetch_errors >= 5:
                    pending_ticker  = "  No server data  "
                    pending_offsets = []
                    ticker_label.color = 0xFF4400

        # Swap in new ticker text and offsets
        if pending_ticker is not None:
            ticker_label.text = pending_ticker
            ticker_offsets    = pending_offsets
            pending_ticker    = None
            pending_offsets   = []

        ticker_x      = DISPLAY_W
        last_triggered = -1    # reset so first vessel flashes on new cycle

    ticker_label.x = ticker_x

    # ── Check if a vessel name has just entered the screen ───
    for (offset, px, py, pidx, entry_width) in ticker_offsets:
        trigger_x = DISPLAY_W - offset
        if (ticker_x <= trigger_x < ticker_x + SCROLL_PX
                and offset != last_triggered):
            flash_vessel   = (px, py, pidx)
            # Flash stops when the full entry has scrolled off left edge
            flash_end_x    = -(offset + entry_width)
            flash_px_count = 0
            flash_bright   = True
            last_triggered = offset
            if 0 <= px < DISPLAY_W and 0 <= py < MAP_H:
                bitmap[px, py] = pidx
            break

    # ── Advance flash state (pixel-based, speed-independent) ─
    if flash_vessel is not None:
        if ticker_x <= flash_end_x:
            # Entry has scrolled off — restore pixel and stop
            fpx, fpy, fpidx = flash_vessel
            if 0 <= fpx < DISPLAY_W and 0 <= fpy < MAP_H:
                bitmap[fpx, fpy] = fpidx
            flash_vessel = None
        else:
            flash_px_count += SCROLL_PX
            if flash_px_count >= FLASH_PX_INTERVAL:
                flash_px_count = 0
                flash_bright   = not flash_bright
                fpx, fpy, fpidx = flash_vessel
                if 0 <= fpx < DISPLAY_W and 0 <= fpy < MAP_H:
                    bitmap[fpx, fpy] = fpidx if flash_bright else P_STALE

    display.refresh(minimum_frames_per_second=0)
    time.sleep(SCROLL_DELAY)
