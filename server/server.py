import asyncio
import websockets
import json
import threading
import http.server
import socketserver
import os
import webview
import urllib.request
import math
import concurrent.futures
from pymavlink import mavutil

MAVLINK_URL = 'udpin:127.0.0.1:14551'
connection = mavutil.mavlink_connection(MAVLINK_URL)

clients = set()
heartbeat_received = False

async def mavlink_listener():
    global heartbeat_received
    print(f"Waiting for MAVLink heartbeat on {MAVLINK_URL}...")
    
    while True:
        msg = connection.recv_match(type=['HEARTBEAT', 'ATTITUDE', 'SERVO_OUTPUT_RAW', 'LOCAL_POSITION_NED', 'VFR_HUD', 'GLOBAL_POSITION_INT', 'TERRAIN_REPORT', 'WIND', 'GPS_RAW_INT', 'SIMSTATE', 'ESTIMATOR_STATUS'], blocking=False)
        if msg:
            if msg.get_type() == 'HEARTBEAT':
                # Ignore GCS (type 6) or non-autopilot component heartbeats so they don't overwrite vehicle telemetry
                if getattr(msg, 'type', None) == mavutil.mavlink.MAV_TYPE_GCS or getattr(msg, 'autopilot', 0) == mavutil.mavlink.MAV_AUTOPILOT_INVALID:
                    await asyncio.sleep(0.005)
                    continue
                if hasattr(msg, 'get_srcComponent') and msg.get_srcComponent() not in [mavutil.mavlink.MAV_COMP_ID_AUTOPILOT1, 1]:
                    await asyncio.sleep(0.005)
                    continue

                if not heartbeat_received:
                    heartbeat_received = True
                    print(f"Autopilot Heartbeat received from Sys {msg.get_srcSystem()}:{msg.get_srcComponent()}! Connected to SITL.")
                    # Request data streams
                    connection.mav.request_data_stream_send(connection.target_system, connection.target_component, mavutil.mavlink.MAV_DATA_STREAM_EXTRA1, 30, 1) # ATTITUDE 30Hz
                    connection.mav.request_data_stream_send(connection.target_system, connection.target_component, mavutil.mavlink.MAV_DATA_STREAM_RC_CHANNELS, 10, 1)
                    connection.mav.request_data_stream_send(connection.target_system, connection.target_component, mavutil.mavlink.MAV_DATA_STREAM_POSITION, 30, 1) # POS 30Hz
                    connection.mav.request_data_stream_send(connection.target_system, connection.target_component, mavutil.mavlink.MAV_DATA_STREAM_EXTRA2, 10, 1) # VFR_HUD
                    connection.mav.request_data_stream_send(connection.target_system, connection.target_component, mavutil.mavlink.MAV_DATA_STREAM_EXTENDED_STATUS, 5, 1) # GPS_RAW_INT & EKF 5Hz
                    
                    # Explicitly request TERRAIN_REPORT (Msg 136) at 2Hz (500,000 microseconds)
                    connection.mav.command_long_send(
                        connection.target_system, connection.target_component,
                        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                        136, 500000, 0, 0, 0, 0, 0
                    )
                    # Stream ArduPlane MAVLink WIND (Msg 168) at 10Hz matching Mission Planner rate
                    connection.mav.command_long_send(
                        connection.target_system, connection.target_component,
                        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                        168, 100000, 0, 0, 0, 0, 0
                    )
                    # Explicitly request GPS_RAW_INT (Msg 24) at 10Hz
                    connection.mav.command_long_send(
                        connection.target_system, connection.target_component,
                        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                        24, 100000, 0, 0, 0, 0, 0
                    )
                    # Explicitly request ESTIMATOR_STATUS (Msg 230) at 10Hz
                    connection.mav.command_long_send(
                        connection.target_system, connection.target_component,
                        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                        230, 100000, 0, 0, 0, 0, 0
                    )
                    # Explicitly request SIMSTATE (Msg 164) at 10Hz (True SITL Physics coordinates)
                    connection.mav.command_long_send(
                        connection.target_system, connection.target_component,
                        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                        164, 100000, 0, 0, 0, 0, 0
                    )
                    connection.mav.request_data_stream_send(connection.target_system, connection.target_component, mavutil.mavlink.MAV_DATA_STREAM_EXTRA3, 5, 1)

            data = {"type": msg.get_type()}
            if msg.get_type() == 'HEARTBEAT':
                # Decode Ardupilot mode strings safely
                mode_str = mavutil.mode_string_v10(msg)
                if mode_str and not mode_str.startswith("Mode("):
                    data['mode'] = mode_str
                else:
                    data['mode'] = getattr(msg, 'flight_mode', 'MANUAL')

                if msg.type == mavutil.mavlink.MAV_TYPE_FIXED_WING or msg.type in [19, 20, 21, 22, 23, 24, 25]:
                    data['firmware'] = 'ArduPlane'
                elif msg.type in [mavutil.mavlink.MAV_TYPE_QUADROTOR, mavutil.mavlink.MAV_TYPE_HEXAROTOR, mavutil.mavlink.MAV_TYPE_OCTOROTOR, mavutil.mavlink.MAV_TYPE_TRICOPTER, mavutil.mavlink.MAV_TYPE_HELICOPTER]:
                    data['firmware'] = 'ArduCopter'
                elif msg.type in [mavutil.mavlink.MAV_TYPE_GROUND_ROVER, mavutil.mavlink.MAV_TYPE_SURFACE_BOAT]:
                    data['firmware'] = 'Rover'
                elif msg.type == mavutil.mavlink.MAV_TYPE_SUBMARINE:
                    data['firmware'] = 'ArduSub'
                else:
                    data['firmware'] = 'ArduPilot'
            elif msg.get_type() == 'ATTITUDE':
                data['roll'] = msg.roll
                data['pitch'] = msg.pitch
                data['yaw'] = msg.yaw
            elif msg.get_type() == 'SERVO_OUTPUT_RAW':
                data['servos'] = [msg.servo1_raw, msg.servo2_raw, msg.servo3_raw, msg.servo4_raw,
                                  msg.servo5_raw, msg.servo6_raw, msg.servo7_raw, msg.servo8_raw]
            elif msg.get_type() == 'LOCAL_POSITION_NED':
                data['x'] = msg.x
                data['y'] = msg.y
                data['z'] = -msg.z # Convert down to up
                data['vx'] = getattr(msg, 'vx', 0.0)
                data['vy'] = getattr(msg, 'vy', 0.0)
            elif msg.get_type() == 'GLOBAL_POSITION_INT':
                data['lat'] = msg.lat / 1e7
                data['lon'] = msg.lon / 1e7
                data['alt'] = msg.alt
                data['relative_alt'] = msg.relative_alt
                data['hdg'] = getattr(msg, 'hdg', 0) / 100.0
            elif msg.get_type() == 'VFR_HUD':
                data['airspeed'] = msg.airspeed
                data['groundspeed'] = msg.groundspeed
                data['heading'] = getattr(msg, 'heading', None)
            elif msg.get_type() == 'WIND':
                data['wind_direction'] = getattr(msg, 'direction', 0)
                data['wind_speed'] = getattr(msg, 'speed', 0.0)
                data['wind_speed_z'] = getattr(msg, 'speed_z', 0.0)
            elif msg.get_type() == 'TERRAIN_REPORT':
                data['terrain_height'] = msg.terrain_height
                data['current_height'] = msg.current_height
            elif msg.get_type() == 'GPS_RAW_INT':
                data['fix_type'] = getattr(msg, 'fix_type', 0)
                data['satellites_visible'] = getattr(msg, 'satellites_visible', 0)
                data['eph'] = getattr(msg, 'eph', 0)
                data['gps_lat'] = getattr(msg, 'lat', 0) / 1e7
                data['gps_lon'] = getattr(msg, 'lon', 0) / 1e7
                data['gps_alt'] = getattr(msg, 'alt', 0) / 1000.0
                data['h_acc'] = getattr(msg, 'h_acc', 0) / 1000.0
            elif msg.get_type() == 'SIMSTATE':
                data['sim_lat'] = getattr(msg, 'lat', 0) / 1e7
                data['sim_lon'] = getattr(msg, 'lng', 0) / 1e7
            elif msg.get_type() == 'ESTIMATOR_STATUS':
                flags = getattr(msg, 'flags', 0)
                data['flags'] = flags
                data['pos_horiz_abs'] = bool(flags & 16)
                data['pred_pos_horiz_abs'] = bool(flags & 512)
                data['gps_glitch'] = bool(flags & 1024)
                data['pos_horiz_ratio'] = getattr(msg, 'pos_horiz_ratio', 0.0)
                data['vel_ratio'] = getattr(msg, 'vel_ratio', 0.0)
                data['innov_ratio'] = max(data.get('pos_horiz_ratio', 0.0), data.get('vel_ratio', 0.0))
                data['pos_horiz_accuracy'] = getattr(msg, 'pos_horiz_accuracy', 0.0)
                data['pos_vert_accuracy'] = getattr(msg, 'pos_vert_accuracy', 0.0)
                
            if clients:
                message = json.dumps(data)
                for client in list(clients):
                    try:
                        await client.send(message)
                    except websockets.exceptions.ConnectionClosed:
                        clients.discard(client)
        await asyncio.sleep(0.005)

async def ws_handler(websocket, path=None):
    clients.add(websocket)
    try:
        async for message in websocket:
            try:
                cmd = json.loads(message)
                action = cmd.get("action")
                if action == "set_param":
                    param_name = cmd.get("name", "")
                    param_val = float(cmd.get("value", 0.0))
                    param_id = param_name.encode('utf-8')[:16]
                    target_sys = getattr(connection, 'target_system', 1) or 1
                    target_comp = getattr(connection, 'target_component', 1) or 1
                    connection.mav.param_set_send(
                        target_sys,
                        target_comp,
                        param_id,
                        param_val,
                        mavutil.mavlink.MAV_PARAM_TYPE_REAL32
                    )
                    print(f"[MAVLink] Sent PARAM_SET: {param_name} = {param_val} to Sys {target_sys}:{target_comp}")
            except Exception as e:
                print(f"[Server] Error processing client message: {e}")
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        clients.discard(websocket)

tile_cache_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tile_cache'))
os.makedirs(tile_cache_dir, exist_ok=True)

precache_state = {
    "is_downloading": False,
    "progress_pct": 0,
    "downloaded": 0,
    "cached": 0,
    "failed": 0,
    "total": 0,
    "status": "Idle"
}

def fetch_google_tile(z, x, y, lyrs='s'):
    mt = abs(x + y) % 4
    url = f"https://mt{mt}.google.com/vt/lyrs={lyrs}&x={x}&y={y}&z={z}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            if resp.status == 200:
                return resp.read()
    except Exception:
        return None
    return None

def get_tiles_for_radius(lat, lon, radius_km, zoom):
    lat_delta = (radius_km / 6371.0) * (180.0 / math.pi)
    lon_delta = (radius_km / (6371.0 * math.cos(math.radians(lat)))) * (180.0 / math.pi)

    def l2t(ln, z): return (ln + 180.0) / 360.0 * (2 ** z)
    def a2t(lt, z):
        rad = math.radians(lt)
        return (1.0 - math.log(math.tan(rad) + 1.0 / math.cos(rad)) / math.pi) / 2.0 * (2 ** z)

    min_x = int(l2t(lon - lon_delta, zoom))
    max_x = int(l2t(lon + lon_delta, zoom))
    min_y = int(a2t(lat + lat_delta, zoom))
    max_y = int(a2t(lat - lat_delta, zoom))

    tiles = []
    for x in range(min(min_x, max_x), max(min_x, max_x) + 1):
        for y in range(min(min_y, max_y), max(min_y, max_y) + 1):
            tiles.append((zoom, x, y))
    return tiles

def run_precache_worker(lat, lon, radius_km, zoom_levels):
    global precache_state
    precache_state["is_downloading"] = True
    precache_state["status"] = "Calculating tiles..."
    
    all_tiles = []
    for z in zoom_levels:
        all_tiles.extend(get_tiles_for_radius(lat, lon, radius_km, z))

    total = len(all_tiles)
    precache_state["total"] = total
    precache_state["downloaded"] = 0
    precache_state["cached"] = 0
    precache_state["failed"] = 0
    precache_state["status"] = f"Downloading {total} tiles..."

    def proc_tile(tile_info):
        z, x, y = tile_info
        tile_path = os.path.join(tile_cache_dir, f"{z}_{x}_{y}.jpg")
        if os.path.exists(tile_path) and os.path.getsize(tile_path) > 100:
            return 'CACHED'
        data = fetch_google_tile(z, x, y)
        if data and len(data) > 100:
            try:
                with open(tile_path, 'wb') as f:
                    f.write(data)
                return 'DOWNLOADED'
            except Exception:
                pass
        return 'FAILED'

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        for idx, res in enumerate(executor.map(proc_tile, all_tiles), start=1):
            if res == 'DOWNLOADED': precache_state["downloaded"] += 1
            elif res == 'CACHED': precache_state["cached"] += 1
            else: precache_state["failed"] += 1
            precache_state["progress_pct"] = int((idx / total) * 100)

    precache_state["is_downloading"] = False
    precache_state["status"] = f"Complete: {precache_state['downloaded'] + precache_state['cached']}/{total} tiles ready"

def start_http_server():
    vis_dir = os.path.join(os.path.dirname(__file__), '..', 'visualizer')
    os.chdir(vis_dir)
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def end_headers(self):
            if not getattr(self, '_is_tile', False):
                self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
                self.send_header('Pragma', 'no-cache')
                self.send_header('Expires', '0')
            super().end_headers()

        def do_GET(self):
            # 1. Tile proxy and disk caching: /tiles/<z>/<x>/<y>.jpg
            if self.path.startswith('/tiles/'):
                self._is_tile = True
                try:
                    clean_path = self.path.split('?')[0]
                    query_str = self.path.split('?')[1] if '?' in self.path else ''
                    query_params = urllib.parse.parse_qs(query_str)
                    mode = query_params.get('mode', ['auto'])[0]
                    lyrs = query_params.get('lyrs', ['s'])[0]
                    parts = clean_path.split('/')
                    if len(parts) >= 5:
                        z = parts[2]
                        x = parts[3]
                        y = parts[4].split('.')[0]
                        suffix = f"_{lyrs}" if lyrs != 's' else ""
                        tile_file = os.path.join(tile_cache_dir, f"{z}_{x}_{y}{suffix}.jpg")
                        if os.path.exists(tile_file) and os.path.getsize(tile_file) > 100:
                            with open(tile_file, 'rb') as f:
                                data = f.read()
                            self.send_response(200)
                            self.send_header('Content-Type', 'image/jpeg')
                            self.send_header('Content-Length', str(len(data)))
                            self.send_header('Cache-Control', 'public, max-age=31536000')
                            self.end_headers()
                            self.wfile.write(data)
                            return
                        elif mode != 'offline':
                            data = fetch_google_tile(int(z), int(x), int(y), lyrs=lyrs)
                            if data:
                                try:
                                    with open(tile_file, 'wb') as f:
                                        f.write(data)
                                except Exception: pass
                                self.send_response(200)
                                self.send_header('Content-Type', 'image/jpeg')
                                self.send_header('Content-Length', str(len(data)))
                                self.send_header('Cache-Control', 'public, max-age=31536000')
                                self.end_headers()
                                self.wfile.write(data)
                                return
                except Exception:
                    pass
                self.send_error(404, "Tile not found")
                return

            # 2. Cache status API: /api/cache_status
            elif self.path.startswith('/api/cache_status'):
                try:
                    cached_files = [f for f in os.listdir(tile_cache_dir) if f.endswith('.jpg')]
                    total_mb = sum(os.path.getsize(os.path.join(tile_cache_dir, f)) for f in cached_files) / (1024 * 1024)
                except Exception:
                    cached_files = []
                    total_mb = 0.0

                resp = {
                    "cached_count": len(cached_files),
                    "cached_mb": round(total_mb, 2),
                    "is_downloading": precache_state["is_downloading"],
                    "progress_pct": precache_state["progress_pct"],
                    "downloaded": precache_state["downloaded"],
                    "cached": precache_state["cached"],
                    "failed": precache_state["failed"],
                    "total": precache_state["total"],
                    "status": precache_state["status"]
                }
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(resp).encode('utf-8'))
                return

            return super().do_GET()

        def do_POST(self):
            if self.path.startswith('/api/cache_region'):
                content_len = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_len).decode('utf-8')
                try:
                    data = json.loads(body)
                    lat = float(data.get('lat', 8.3105))
                    lon = float(data.get('lon', 77.3137))
                    radius = float(data.get('radius_km', 3.0))
                    zooms = data.get('zooms', [18])
                    if not precache_state["is_downloading"]:
                        threading.Thread(target=run_precache_worker, args=(lat, lon, radius, zooms), daemon=True).start()
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "started"}).encode('utf-8'))
                except Exception as e:
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
                return

            return super().do_POST()

        def log_message(self, format, *args): pass
    
    try:
        # Use ThreadingHTTPServer so a single browser's Keep-Alive doesn't block other connections
        with http.server.ThreadingHTTPServer(("0.0.0.0", 8000), QuietHandler) as httpd:
            print("HTTP Web Server with Offline Tile Cache started on port 8000")
            httpd.serve_forever()
    except OSError as e:
        if getattr(e, 'errno', None) in (10048, 98):
            print("[Notice] HTTP Port 8000 is already in use by an active server.")
        else:
            raise

async def main():
    # Start the HTTP server in the background
    threading.Thread(target=start_http_server, daemon=True).start()

    try:
        server = await websockets.serve(ws_handler, "0.0.0.0", 8766)
        print("WebSocket Server started on port 8766")
        await asyncio.gather(server.wait_closed(), mavlink_listener())
    except OSError as e:
        if getattr(e, 'errno', None) in (10048, 98):
            print("\n" + "="*65)
            print(" [!] ERROR: Port 8766 is already in use by another Python instance.")
            print(" An existing server.py process is already running.")
            print(" To free the port, run in PowerShell:")
            print("   Get-Process python | Stop-Process -Force")
            print("="*65 + "\n")
        raise

def start_asyncio_loop():
    # Set up a new event loop for this background thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())

class Api:
    def open_cesium(self):
        webview.create_window(
            'Cesium 3D Terrain Map', 
            'http://127.0.0.1:8000/cesium.html', 
            width=1280, 
            height=720,
            background_color='#000000'
        )

def open_browser(url):
    import platform
    import subprocess
    import shutil
    import webbrowser

    # Check if running in Windows Subsystem for Linux (WSL)
    is_wsl = 'microsoft' in platform.uname().release.lower() or os.path.exists('/proc/sys/fs/binfmt_misc/WSLInterop')
    if is_wsl:
        # Launch directly into the user's Windows default browser tab
        if shutil.which("cmd.exe"):
            try:
                subprocess.Popen(["cmd.exe", "/c", "start", "", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except Exception:
                pass
        if shutil.which("powershell.exe"):
            try:
                subprocess.Popen(["powershell.exe", "-NoProfile", "-Command", f"Start-Process '{url}'"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except Exception:
                pass
        if shutil.which("wslview"):
            try:
                subprocess.Popen(["wslview", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except Exception:
                pass

    # Standard browser launch for native Windows/macOS/Linux
    try:
        webbrowser.open(url)
    except Exception:
        pass

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ArduPilot SITL Telemetry & Visualizer Server")
    parser.add_argument("--headless", "--no-gui", action="store_true", help="Run without native desktop window (headless mode for WSL/Linux)")
    args = parser.parse_args()

    # Ensure Windows taskbar displays the custom app icon instead of generic python.exe
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('ardupilot.sitl.visualizer.1.0')
    except Exception:
        pass

    icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app_icon.ico')

    api = Api()

    if args.headless:
        print("\n[Server] Running in Headless Server Mode (--headless).")
        print("[Visualizer] Opening browser tab at: http://127.0.0.1:8000/sharkee.html\n")
        open_browser("http://127.0.0.1:8000/sharkee.html")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(main())
        except KeyboardInterrupt:
            print("\nShutting down server.")
    else:
        # 1. Start the asyncio background logic (MAVLink + WebSockets + HTTP server) in a separate thread
        server_thread = threading.Thread(target=start_asyncio_loop, daemon=True)
        server_thread.start()
        
        # 2. Launch the native desktop window on the main thread (with fallback if GTK/QT unavailable in WSL)
        try:
            window = webview.create_window(
                'Shark Hawk Digital Twin', 
                'http://127.0.0.1:8000/sharkee.html', 
                js_api=api,
                width=1280, 
                height=720,
                background_color='#000000'
            )
            webview.start(icon=icon_path if os.path.exists(icon_path) else None)
        except Exception as e:
            print(f"\n[Notice] Native GUI window could not be started: {e}")
            print("[Server] Falling back to Headless Server Mode.")
            print("[Visualizer] Opening in your browser tab at: http://127.0.0.1:8000/sharkee.html\n")
            open_browser("http://127.0.0.1:8000/sharkee.html")
            try:
                while server_thread.is_alive():
                    server_thread.join(timeout=1.0)
            except KeyboardInterrupt:
                print("\nShutting down server.")



