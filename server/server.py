import asyncio
import websockets
import json
import threading
import http.server
import socketserver
import os
import webbrowser
from pymavlink import mavutil

MAVLINK_URL = 'udpin:127.0.0.1:14551'
connection = mavutil.mavlink_connection(MAVLINK_URL)

clients = set()
heartbeat_received = False

async def mavlink_listener():
    global heartbeat_received
    print(f"Waiting for MAVLink heartbeat on {MAVLINK_URL}...")
    
    while True:
        msg = connection.recv_match(type=['HEARTBEAT', 'ATTITUDE', 'SERVO_OUTPUT_RAW', 'LOCAL_POSITION_NED', 'VFR_HUD', 'GLOBAL_POSITION_INT', 'TERRAIN_REPORT'], blocking=False)
        if msg:
            if not heartbeat_received and msg.get_type() == 'HEARTBEAT':
                heartbeat_received = True
                print("Heartbeat received! Connected to SITL.")
                # Request data streams
                connection.mav.request_data_stream_send(connection.target_system, connection.target_component, mavutil.mavlink.MAV_DATA_STREAM_EXTRA1, 30, 1) # ATTITUDE 30Hz
                connection.mav.request_data_stream_send(connection.target_system, connection.target_component, mavutil.mavlink.MAV_DATA_STREAM_RC_CHANNELS, 10, 1)
                connection.mav.request_data_stream_send(connection.target_system, connection.target_component, mavutil.mavlink.MAV_DATA_STREAM_POSITION, 30, 1) # POS 30Hz
                connection.mav.request_data_stream_send(connection.target_system, connection.target_component, mavutil.mavlink.MAV_DATA_STREAM_EXTRA2, 10, 1) # VFR_HUD

            data = {"type": msg.get_type()}
            if msg.get_type() == 'HEARTBEAT':
                # Decode Ardupilot mode strings
                data['mode'] = mavutil.mode_string_v10(msg)
                if msg.type == mavutil.mavlink.MAV_TYPE_FIXED_WING:
                    data['firmware'] = 'ArduPlane'
                elif msg.type in [mavutil.mavlink.MAV_TYPE_QUADROTOR, mavutil.mavlink.MAV_TYPE_HEXAROTOR, mavutil.mavlink.MAV_TYPE_OCTOROTOR]:
                    data['firmware'] = 'ArduCopter'
                else:
                    data['firmware'] = f'Type {msg.type}'
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
            elif msg.get_type() == 'GLOBAL_POSITION_INT':
                data['lat'] = msg.lat / 1e7
                data['lon'] = msg.lon / 1e7
            elif msg.get_type() == 'VFR_HUD':
                data['airspeed'] = msg.airspeed
                data['groundspeed'] = msg.groundspeed
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
    
    # Auto-open the visualizer in the default browser after 1 second
    threading.Timer(1.0, lambda: webbrowser.open('http://127.0.0.1:8000')).start()

    server = await websockets.serve(ws_handler, "0.0.0.0", 8766)
    print("WebSocket Server started on port 8766")
    await asyncio.gather(server.wait_closed(), mavlink_listener())

if __name__ == "__main__":
    asyncio.run(main())
