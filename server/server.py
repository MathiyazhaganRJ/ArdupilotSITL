import asyncio
import websockets
import json
import threading
import http.server
import socketserver
import os
import webview
from pymavlink import mavutil

MAVLINK_URL = 'udpin:127.0.0.1:14551'
connection = mavutil.mavlink_connection(MAVLINK_URL)

clients = set()
heartbeat_received = False

async def mavlink_listener():
    global heartbeat_received
    print(f"Waiting for MAVLink heartbeat on {MAVLINK_URL}...")
    
    while True:
        msg = connection.recv_match(type=['HEARTBEAT', 'ATTITUDE', 'SERVO_OUTPUT_RAW', 'LOCAL_POSITION_NED', 'VFR_HUD', 'GLOBAL_POSITION_INT', 'TERRAIN_REPORT', 'WIND'], blocking=False)
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
                    
                    # Explicitly request TERRAIN_REPORT (Msg 136) at 2Hz (500,000 microseconds)
                    connection.mav.command_long_send(
                        connection.target_system, connection.target_component,
                        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                        136, 500000, 0, 0, 0, 0, 0
                    )
                    connection.mav.request_data_stream_send(connection.target_system, connection.target_component, mavutil.mavlink.MAV_DATA_STREAM_EXTRA3, 2, 1)

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
        await websocket.wait_closed()
    finally:
        clients.discard(websocket)

def start_http_server():
    vis_dir = os.path.join(os.path.dirname(__file__), '..', 'visualizer')
    os.chdir(vis_dir)
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args): pass
    
    # Use ThreadingHTTPServer so a single browser's Keep-Alive doesn't block other connections
    with http.server.ThreadingHTTPServer(("0.0.0.0", 8000), QuietHandler) as httpd:
        print("HTTP Web Server started on port 8000")
        httpd.serve_forever()

async def main():
    # Start the HTTP server in the background
    threading.Thread(target=start_http_server, daemon=True).start()

    server = await websockets.serve(ws_handler, "0.0.0.0", 8766)
    print("WebSocket Server started on port 8766")
    await asyncio.gather(server.wait_closed(), mavlink_listener())

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



