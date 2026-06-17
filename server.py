import asyncio
import websockets
import json
from pymavlink import mavutil

MAVLINK_URL = 'udpin:127.0.0.1:14555'
connection = mavutil.mavlink_connection(MAVLINK_URL)

clients = set()
heartbeat_received = False

async def mavlink_listener():
    global heartbeat_received
    print(f"Waiting for MAVLink heartbeat on {MAVLINK_URL}...")
    
    while True:
        msg = connection.recv_match(type=['HEARTBEAT', 'ATTITUDE', 'SERVO_OUTPUT_RAW', 'LOCAL_POSITION_NED', 'VFR_HUD'], blocking=False)
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
            elif msg.get_type() == 'VFR_HUD':
                data['airspeed'] = msg.airspeed
                data['groundspeed'] = msg.groundspeed
                
            if clients:
                message = json.dumps(data)
                for client in list(clients):
                    try:
                        await client.send(message)
                    except websockets.exceptions.ConnectionClosed:
                        clients.remove(client)
        await asyncio.sleep(0.005)

async def ws_handler(websocket, path=None):
    clients.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        clients.remove(websocket)

async def main():
    server = await websockets.serve(ws_handler, "127.0.0.1", 8766)
    print("WebSocket Server started on ws://127.0.0.1:8766")
    await asyncio.gather(server.wait_closed(), mavlink_listener())

if __name__ == "__main__":
    asyncio.run(main())
