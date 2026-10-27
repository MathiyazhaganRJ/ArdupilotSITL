import math
import os
import time
import asyncio
import websockets
import threading
import json
import webview
from pymavlink import mavutil
import http.server
import socketserver
import math
import copy
import array

def sanitize_json(obj):
    if isinstance(obj, float):
        return None if math.isnan(obj) or math.isinf(obj) else obj
    elif isinstance(obj, dict):
        return {k: sanitize_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple, array.array)):
        return [sanitize_json(v) for v in obj]
    elif isinstance(obj, (bytes, bytearray)):
        return obj.decode('utf-8', errors='ignore')
    return obj

clients = set()
global_loop = None

async def ws_handler(websocket, path=None):
    clients.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        clients.discard(websocket)

import array

async def broadcast_msg(msg_dict):
    if not clients: return
    msg = json.dumps(sanitize_json(msg_dict))
    for c in list(clients):
        try:
            await c.send(msg)
        except:
            pass

class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

def start_http_server():
    vis_dir = os.path.join(os.path.dirname(__file__), 'visualizer')
    os.chdir(vis_dir)
    handler = NoCacheHandler
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", 8000), handler) as httpd:
        httpd.serve_forever()

class Api:
    def __init__(self):
        pass

    def load_log(self):
        import tkinter as tk
        from tkinter import filedialog
        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            file_path = filedialog.askopenfilename(
                title="Select ArduPilot Log",
                filetypes=[("Log Files", "*.bin *.tlog"), ("All Files", "*.*")]
            )
            root.destroy()
            
            if file_path:
                if global_loop:
                    asyncio.run_coroutine_threadsafe(broadcast_msg({'type': 'LOADING', 'file': file_path}), global_loop)
                threading.Thread(target=self._parse_log_thread, args=(file_path,), daemon=True).start()
                return {"success": True, "file": file_path}
            return {"success": False}
        except Exception as e:
            print("Dialog error:", e)
            return {"success": False}

    def _parse_log_thread(self, file_path):
        try:
            conn = mavutil.mavlink_connection(file_path)
            trajectory = []
            params = {}
            current_state = {}
            
            last_att = [0.0, 0.0, 0.0]
            last_servos = [1000] * 8
            last_vfr = [0.0, 0.0]
            last_mode = "UNKNOWN"
            last_gps_time = ""
            
            valid_types = [
                'PARM', 'PARAM_VALUE', 'GLOBAL_POSITION_INT', 'ATTITUDE', 'GPS', 'ATT', 
                'SERVO_OUTPUT_RAW', 'VFR_HUD', 'HEARTBEAT', 'RCOU', 'ARSP', 'MODE', 'POS',
                'BAT', 'IMU', 'RCIN', 'NKF1', 'NKF2', 'NKF3', 'NKF4', 'CTRL', 'CTUN', 
                'NTUN', 'MAG', 'BARO', 'AHR2', 'TERR', 'STAT', 'FMT', 'FMTU'
            ]
            
            while True:
                m = conn.recv_match(type=valid_types, blocking=False)
                if m is None:
                    break
                    
                t = m.get_type()
                
                if t in ['FMT', 'FMTU', 'MULT', 'MSG', 'BAD_DATA']:
                    continue
                    
                if t == 'PARM':
                    params[getattr(m, 'Name', '')] = getattr(m, 'Value', 0)
                    continue
                elif t == 'PARAM_VALUE':
                    params[getattr(m, 'param_id', '')] = getattr(m, 'param_value', 0)
                    continue
                    
                try:
                    md = m.to_dict()
                    md.pop('mavpackettype', None)
                    md.pop('TimeUS', None)
                    
                    current_state[t] = sanitize_json(md)
                except:
                    pass
                    
                if t == 'ATTITUDE':
                    last_att = [m.roll, m.pitch, m.yaw]
                elif t == 'ATT':
                    last_att = [getattr(m, 'Roll', 0)*3.14159/180.0, getattr(m, 'Pitch', 0)*3.14159/180.0, getattr(m, 'Yaw', 0)*3.14159/180.0]
                elif t == 'GLOBAL_POSITION_INT':
                    trajectory.append([m.lat / 1e7, m.lon / 1e7, m.relative_alt / 1000.0, *last_att, list(last_servos), list(last_vfr), last_mode, last_gps_time])
                elif t == 'GPS':
                    if hasattr(m, 'Spd'): last_vfr[1] = m.Spd
                    elif hasattr(m, 'SpdGnd'): last_vfr[1] = m.SpdGnd
                    
                    gwk = getattr(m, 'GWk', 0)
                    gms = getattr(m, 'GMS', 0)
                    time_us = getattr(m, 'TimeUS', 0)
                    if gwk > 0 and gms > 0:
                        epoch = 315964800000 + (gwk * 604800000) + gms
                        last_gps_time = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(epoch / 1000.0))
                    elif time_us > 0:
                        sec = time_us // 1000000
                        last_gps_time = f"{sec // 60:02d}:{sec % 60:02d}"
                elif t == 'POS':
                    if hasattr(m, 'Lat') and hasattr(m, 'Lng'):
                        lat = m.Lat if m.Lat < 1000 else m.Lat / 1e7
                        lng = m.Lng if m.Lng < 1000 else m.Lng / 1e7
                        alt = getattr(m, 'Alt', 0)
                        trajectory.append([lat, lng, alt, *last_att, list(last_servos), list(last_vfr), last_mode, last_gps_time])
                elif t == 'SERVO_OUTPUT_RAW':
                    last_servos = [m.servo1_raw, m.servo2_raw, m.servo3_raw, m.servo4_raw, m.servo5_raw, m.servo6_raw, m.servo7_raw, m.servo8_raw]
                elif t == 'RCOU':
                    last_servos = [getattr(m, f'C{i}', 1000) for i in range(1, 9)]
                elif t == 'VFR_HUD':
                    last_vfr = [m.airspeed, m.groundspeed]
                elif t == 'ARSP':
                    if hasattr(m, 'Airspeed'): last_vfr[0] = m.Airspeed
                elif t == 'HEARTBEAT':
                    last_mode = mavutil.mode_string_v10(m)
                elif t == 'MODE':
                    if hasattr(m, 'Mode'): last_mode = str(m.Mode)
                    elif hasattr(m, 'ModeNum'): last_mode = f"Mode({m.ModeNum})"
                        
            if len(trajectory) > 0:
                # Normalize altitude to relative if it was absolute
                first_alt = trajectory[0][2]
                for pt in trajectory:
                    pt[2] = pt[2] - first_alt
                    
            if global_loop:
                asyncio.run_coroutine_threadsafe(broadcast_msg({
                    'type': 'FULL_PATH', 
                    'data': trajectory,
                    'params': params
                }), global_loop)
        except Exception as e:
            import traceback
            traceback.print_exc()
            if global_loop:
                asyncio.run_coroutine_threadsafe(broadcast_msg({'type': 'ERROR', 'message': str(e)}), global_loop)

async def main(api_instance):
    global global_loop
    global_loop = asyncio.get_running_loop()
    threading.Thread(target=start_http_server, daemon=True).start()
    async with websockets.serve(ws_handler, "localhost", 8766, reuse_address=True, max_size=None):
        await asyncio.Future()

def start_asyncio_loop(api_instance):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main(api_instance))

if __name__ == "__main__":
    import argparse
    import webbrowser

    parser = argparse.ArgumentParser(description="ArduPilot Log Viewer")
    parser.add_argument("--headless", "--no-gui", action="store_true", help="Run without native desktop window (headless mode for WSL/Linux)")
    args = parser.parse_args()

    # Ensure Windows taskbar displays the custom app icon instead of generic python.exe
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('ardupilot.logviewer.app.1.0')
    except Exception:
        pass

    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app_icon.ico')

    api = Api()

    if args.headless:
        print("\n[Server] Running in Headless Server Mode (--headless).")
        print("[Visualizer] Open in your browser at: http://127.0.0.1:8000/log_viewer.html\n")
        try:
            webbrowser.open("http://127.0.0.1:8000/log_viewer.html")
        except Exception:
            pass
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(main(api))
        except KeyboardInterrupt:
            print("\nShutting down log viewer.")
    else:
        server_thread = threading.Thread(target=start_asyncio_loop, args=(api,), daemon=True)
        server_thread.start()

        try:
            window = webview.create_window(
                'Ardupilot Log Viewer', 
                f'http://127.0.0.1:8000/log_viewer.html?ts={time.time()}', 
                width=1280, 
                height=720,
                background_color='#000000',
                js_api=api
            )
            webview.start(icon=icon_path if os.path.exists(icon_path) else None)
        except Exception as e:
            print(f"\n[Notice] Native GUI window could not be started: {e}")
            print("[Server] Falling back to Headless Server Mode.")
            print("[Visualizer] Access in your browser at: http://127.0.0.1:8000/log_viewer.html\n")
            try:
                webbrowser.open("http://127.0.0.1:8000/log_viewer.html")
            except Exception:
                pass
            try:
                while server_thread.is_alive():
                    server_thread.join(timeout=1.0)
            except KeyboardInterrupt:
                print("\nShutting down log viewer.")


