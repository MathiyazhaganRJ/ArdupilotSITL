import asyncio
import websockets
import json
import time
import threading
import http.server
import socketserver
import os
import re
import shutil
import webview
import urllib.request
import math
import concurrent.futures
import sys
from pymavlink import mavutil

# Ensure current directory is in sys.path for sibling module imports without triggering circular import
_server_dir = os.path.dirname(os.path.abspath(__file__))
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

try:
    from board_types import resolve_board_name, format_fc_board_name
except ImportError:
    def resolve_board_name(*args, **kwargs): return "SITL"
    def format_fc_board_name(name): return name

def parse_mavlink_target():
    target = os.environ.get('MAVLINK_URL', 'udpin:127.0.0.1:14551')
    baud = 115200
    for i, arg in enumerate(sys.argv):
        if arg in ('--connect', '--mavlink', '-c') and i + 1 < len(sys.argv):
            target = sys.argv[i + 1]
            break
        elif arg.startswith(('--connect=', '--mavlink=')):
            target = arg.split('=', 1)[1]
            break
    if ':' in target and not target.startswith(('udp', 'tcp')):
        parts = target.split(':')
        target = parts[0]
        try:
            baud = int(parts[1])
        except ValueError:
            pass
    if target.lower().startswith('com'):
        target = target.upper()
    return target, baud

MAVLINK_DEVICE, MAVLINK_BAUD = parse_mavlink_target()
MAVLINK_URL = f'{MAVLINK_DEVICE}:{MAVLINK_BAUD}' if not MAVLINK_DEVICE.startswith(('udp', 'tcp')) else MAVLINK_DEVICE
if MAVLINK_DEVICE.startswith(('udp', 'tcp')):
    print(f"[MAVLink] Connecting via network: {MAVLINK_DEVICE}")
    connection = mavutil.mavlink_connection(MAVLINK_DEVICE)
else:
    print(f"[MAVLink] Connecting to serial port {MAVLINK_DEVICE} at {MAVLINK_BAUD} baud...")
    connection = mavutil.mavlink_connection(MAVLINK_DEVICE, baud=MAVLINK_BAUD)

clients = set()
heartbeat_received = False
is_network_sitl = MAVLINK_DEVICE.startswith(('udp', 'tcp')) and any(h in MAVLINK_DEVICE for h in ('127.0.0.1', 'localhost', '0.0.0.0'))
detected_fc_hardware = "SITL" if is_network_sitl else "Hardware FC"
detected_firmware = "ArduPlane"
capabilities_requested = False
last_version_req_time = 0

class MissionHandler:
    def __init__(self, mav_conn):
        self.conn = mav_conn
        self.waypoints = []
        self._pending_waypoints = []
        self.current_seq = 0
        self.is_fetching = False
        self.expected_count = 0
        self.next_req_seq = 0
        self.last_req_time = 0
        self.retries = 0
        self.max_retries = 5
        self.target_system = 1
        self.target_component = 1
        self._just_finished_fetch_time = 0
        self._last_out_of_sync_fetch = 0
        self.cache_file = os.path.abspath(os.path.join(os.path.dirname(__file__), 'waypoints_cache.json'))
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as cf:
                    cached = json.load(cf)
                    if isinstance(cached, list) and len(cached) > 0:
                        self.waypoints = cached
                        print(f"[Mission] Loaded {len(self.waypoints)} cached waypoints from disk on startup")
        except Exception as e:
            print(f"[Mission] Error reading waypoint cache: {e}")

    def start_fetch(self, force=False):
        if not self.conn:
            return False
        now = time.time()
        if self.is_fetching and (now - self.last_req_time < 2.0) and not force:
            print("[Mission] Fetch already in progress, ignoring duplicate request")
            return False
        target_sys = getattr(self, 'target_system', None) or getattr(self.conn, 'target_system', 1) or 1
        target_comp = getattr(self, 'target_component', None) or getattr(self.conn, 'target_component', 1) or 1
        self.is_fetching = True
        self.expected_count = 0
        self.next_req_seq = 0
        self.retries = 0
        self.last_req_time = now
        self._pending_waypoints = []
        try:
            try:
                self.conn.mav.mission_request_list_send(target_sys, target_comp, 0)
            except TypeError:
                self.conn.mav.mission_request_list_send(target_sys, target_comp)
            print(f"[Mission] Requested mission list from Sys {target_sys}:{target_comp}")
            return True
        except Exception as e:
            print(f"[Mission] Error requesting mission list: {e}")
            self.is_fetching = False
            return False

    def request_item(self, seq):
        target_sys = getattr(self, 'target_system', None) or getattr(self.conn, 'target_system', 1) or 1
        target_comp = getattr(self, 'target_component', None) or getattr(self.conn, 'target_component', 1) or 1
        self.last_req_time = time.time()
        try:
            if hasattr(self.conn.mav, 'mission_request_int_send') and (self.retries % 2 == 0):
                try:
                    self.conn.mav.mission_request_int_send(target_sys, target_comp, seq, 0)
                except TypeError:
                    self.conn.mav.mission_request_int_send(target_sys, target_comp, seq)
            else:
                try:
                    self.conn.mav.mission_request_send(target_sys, target_comp, seq, 0)
                except TypeError:
                    self.conn.mav.mission_request_send(target_sys, target_comp, seq)
        except Exception as e:
            print(f"[Mission] Error requesting item {seq}: {e}")

    def set_current(self, seq):
        target_sys = getattr(self, 'target_system', None) or getattr(self.conn, 'target_system', 1) or 1
        target_comp = getattr(self, 'target_component', None) or getattr(self.conn, 'target_component', 1) or 1
        try:
            self.conn.mav.mission_set_current_send(target_sys, target_comp, int(seq))
            print(f"[Mission] Sent MISSION_SET_CURRENT seq {seq}")
        except Exception as e:
            print(f"[Mission] Error setting current WP: {e}")

    def handle_msg(self, msg):
        mtype = msg.get_type()
        src_sys = getattr(msg, 'get_srcSystem', lambda: 1)()
        src_comp = getattr(msg, 'get_srcComponent', lambda: 1)()
        if src_sys:
            self.target_system = src_sys
        if src_comp:
            self.target_component = src_comp
        target_sys = getattr(self, 'target_system', 1) or 1
        target_comp = getattr(self, 'target_component', 1) or 1

        if mtype == 'MISSION_COUNT':
            count = msg.count
            print(f"[Mission] Vehicle reported {count} mission items")
            self.expected_count = count
            self._pending_waypoints = [None] * count
            self.next_req_seq = 0
            self.retries = 0
            self.is_fetching = True
            self.last_req_time = time.time()
            if count > 0:
                self.request_item(0)
            else:
                self.is_fetching = False
                self.waypoints = []
                self._just_finished_fetch_time = time.time()
                try:
                    with open(self.cache_file, 'w', encoding='utf-8') as cf:
                        json.dump([], cf, indent=2)
                except Exception as e:
                    print(f"[Mission] Error writing empty waypoint cache: {e}")
                return {
                    "type": "MISSION_WAYPOINTS",
                    "waypoints": [],
                    "count": 0,
                    "current_seq": self.current_seq
                }

        elif mtype in ['MISSION_ITEM_INT', 'MISSION_ITEM']:
            seq = msg.seq
            is_int = (mtype == 'MISSION_ITEM_INT')
            lat = (msg.x / 1e7) if is_int else msg.x
            lon = (msg.y / 1e7) if is_int else msg.y
            cmd_code = msg.command

            item = {
                "seq": seq,
                "command": cmd_code,
                "frame": msg.frame,
                "lat": lat,
                "lon": lon,
                "alt": getattr(msg, 'z', 0.0),
                "param1": getattr(msg, 'param1', 0.0),
                "param2": getattr(msg, 'param2', 0.0),
                "param3": getattr(msg, 'param3', 0.0),
                "param4": getattr(msg, 'param4', 0.0),
                "current": getattr(msg, 'current', 0),
                "autocontinue": getattr(msg, 'autocontinue', 1)
            }

            if hasattr(self, '_pending_waypoints') and 0 <= seq < len(self._pending_waypoints):
                self._pending_waypoints[seq] = item
            elif 0 <= seq < len(self.waypoints):
                self.waypoints[seq] = item

            if self.is_fetching and hasattr(self, '_pending_waypoints') and self._pending_waypoints:
                missing = [i for i, w in enumerate(self._pending_waypoints) if w is None]
                if not missing:
                    self.is_fetching = False
                    self._just_finished_fetch_time = time.time()
                    try:
                        self.conn.mav.mission_ack_send(
                            target_sys, target_comp,
                            mavutil.mavlink.MAV_MISSION_ACCEPTED
                        )
                    except Exception: pass
                    valid_wps = [w for w in self._pending_waypoints if w is not None]
                    self.waypoints = valid_wps
                    print(f"[Mission] Successfully downloaded {len(valid_wps)} waypoints")
                    try:
                        with open(self.cache_file, 'w', encoding='utf-8') as cf:
                            json.dump(valid_wps, cf, indent=2)
                    except Exception as e:
                        print(f"[Mission] Error writing waypoint cache: {e}")
                    return {
                        "type": "MISSION_WAYPOINTS",
                        "waypoints": valid_wps,
                        "count": len(valid_wps),
                        "current_seq": self.current_seq
                    }
                else:
                    self.next_req_seq = missing[0]
                    self.retries = 0
                    self.request_item(self.next_req_seq)

        elif mtype == 'MISSION_ACK':
            ack_type = getattr(msg, 'type', 0)
            now = time.time()
            if ack_type == mavutil.mavlink.MAV_MISSION_ACCEPTED:
                # If vehicle accepted a mission from another GCS/MAVProxy and not our own download completion
                if now - getattr(self, '_just_finished_fetch_time', 0) > 3.0:
                    print(f"[Mission] Vehicle accepted new mission (MISSION_ACK). Triggering automatic download...")
                    self.start_fetch(force=True)

        elif mtype == 'MISSION_CURRENT':
            self.current_seq = msg.seq
            # If vehicle current seq is beyond cached waypoints, waypoints are out-of-date
            if self.waypoints and msg.seq >= len(self.waypoints):
                now = time.time()
                if now - getattr(self, '_last_out_of_sync_fetch', 0) > 5.0:
                    self._last_out_of_sync_fetch = now
                    print(f"[Mission] Vehicle current seq {msg.seq} exceeds cached count {len(self.waypoints)}. Re-fetching mission...")
                    self.start_fetch(force=True)
            return {
                "type": "MISSION_CURRENT",
                "seq": msg.seq
            }

        elif mtype == 'MISSION_ITEM_REACHED':
            return {
                "type": "MISSION_ITEM_REACHED",
                "seq": msg.seq
            }

        elif mtype == 'NAV_CONTROLLER_OUTPUT':
            return {
                "type": "NAV_CONTROLLER_OUTPUT",
                "wp_dist": getattr(msg, 'wp_dist', 0),
                "nav_bearing": getattr(msg, 'nav_bearing', 0),
                "nav_roll": getattr(msg, 'nav_roll', 0.0),
                "nav_pitch": getattr(msg, 'nav_pitch', 0.0),
                "alt_error": getattr(msg, 'alt_error', 0.0),
                "aspd_error": getattr(msg, 'aspd_error', 0.0),
                "xtrack_error": getattr(msg, 'xtrack_error', 0.0)
            }

        return None

    def check_timeout(self):
        if not self.is_fetching:
            return None
        now = time.time()
        # Case 1: Waiting for MISSION_COUNT from vehicle
        if self.expected_count == 0:
            if now - self.last_req_time > 1.5:
                if self.retries < self.max_retries:
                    self.retries += 1
                    self.last_req_time = now
                    target_sys = getattr(self, 'target_system', None) or getattr(self.conn, 'target_system', 1) or 1
                    target_comp = getattr(self, 'target_component', None) or getattr(self.conn, 'target_component', 1) or 1
                    print(f"[Mission] Retry #{self.retries} requesting mission list from Sys {target_sys}:{target_comp}")
                    try:
                        try:
                            self.conn.mav.mission_request_list_send(target_sys, target_comp, 0)
                        except TypeError:
                            self.conn.mav.mission_request_list_send(target_sys, target_comp)
                    except Exception as e:
                        print(f"[Mission] Error resending mission request list: {e}")
                else:
                    print(f"[Mission] Timeout waiting for MISSION_COUNT after {self.max_retries} retries")
                    self.is_fetching = False
            return None

        # Case 2: Waiting for individual mission items
        if now - self.last_req_time > 1.2:
            if hasattr(self, '_pending_waypoints') and self._pending_waypoints:
                missing = [i for i, w in enumerate(self._pending_waypoints) if w is None]
                if not missing:
                    self.is_fetching = False
                    self._just_finished_fetch_time = time.time()
                    valid_wps = [w for w in self._pending_waypoints if w is not None]
                    self.waypoints = valid_wps
                    try:
                        with open(self.cache_file, 'w', encoding='utf-8') as cf:
                            json.dump(valid_wps, cf, indent=2)
                    except Exception: pass
                    return {
                        "type": "MISSION_WAYPOINTS",
                        "waypoints": valid_wps,
                        "count": len(valid_wps),
                        "current_seq": self.current_seq
                    }
                if self.retries < self.max_retries:
                    self.retries += 1
                    self.next_req_seq = missing[0]
                    print(f"[Mission] Retry #{self.retries} requesting seq {self.next_req_seq}")
                    self.request_item(self.next_req_seq)
                else:
                    print(f"[Mission] Timeout downloading mission items after {self.max_retries} retries (have {len(self._pending_waypoints) - len(missing)}/{self.expected_count})")
                    self.is_fetching = False
                    valid_wps = [w for w in self._pending_waypoints if w is not None]
                    if valid_wps:
                        self.waypoints = valid_wps
                        return {
                            "type": "MISSION_WAYPOINTS",
                            "waypoints": valid_wps,
                            "count": len(valid_wps),
                            "current_seq": self.current_seq
                        }
            else:
                self.is_fetching = False
        return None

heartbeat_received = False
cached_home_position = None
cached_statustext_messages = []
cached_heartbeat = None
mission_handler = MissionHandler(connection)

async def mavlink_listener():
    global heartbeat_received, cached_home_position, cached_statustext_messages, cached_heartbeat, detected_firmware, detected_fc_hardware, last_version_req_time
    print(f"Waiting for MAVLink heartbeat on {MAVLINK_URL}...")
    
    while True:
        msg = connection.recv_match(
            type=['HEARTBEAT', 'ATTITUDE', 'AUTOPILOT_VERSION', 'SERVO_OUTPUT_RAW', 'LOCAL_POSITION_NED', 'VFR_HUD',
                  'ESC_TELEMETRY_1_TO_4', 'ESC_TELEMETRY_5_TO_8', 'ESC_TELEMETRY_9_TO_12', 'ESC_STATUS', 'BATTERY_STATUS', 'SYS_STATUS',
                  'GLOBAL_POSITION_INT', 'TERRAIN_REPORT', 'WIND', 'GPS_RAW_INT', 'SIMSTATE',
                  'ESTIMATOR_STATUS', 'MISSION_COUNT', 'MISSION_ITEM_INT', 'MISSION_ITEM',
                  'MISSION_CURRENT', 'MISSION_ITEM_REACHED', 'MISSION_ACK', 'NAV_CONTROLLER_OUTPUT', 'HOME_POSITION',
                  'STATUSTEXT', 'PARAM_VALUE'],
            blocking=False
        )
        timeout_res = mission_handler.check_timeout()
        if timeout_res and clients:
            t_str = json.dumps(timeout_res)
            for client in list(clients):
                try:
                    await client.send(t_str)
                except websockets.exceptions.ConnectionClosed:
                    clients.discard(client)

        if msg:
            mission_res = mission_handler.handle_msg(msg)
            if mission_res and clients:
                msg_str = json.dumps(mission_res)
                for client in list(clients):
                    try:
                        await client.send(msg_str)
                    except websockets.exceptions.ConnectionClosed:
                        clients.discard(client)

            if msg.get_type() == 'HEARTBEAT':
                # Ignore GCS (type 6) or non-autopilot component heartbeats so they don't overwrite vehicle telemetry
                if getattr(msg, 'type', None) == mavutil.mavlink.MAV_TYPE_GCS or getattr(msg, 'autopilot', 0) == mavutil.mavlink.MAV_AUTOPILOT_INVALID:
                    await asyncio.sleep(0.005)
                    continue
                if hasattr(msg, 'get_srcComponent') and msg.get_srcComponent() not in [mavutil.mavlink.MAV_COMP_ID_AUTOPILOT1, 1]:
                    await asyncio.sleep(0.005)
                    continue

                connection.target_system = msg.get_srcSystem()
                connection.target_component = msg.get_srcComponent()
                mission_handler.target_system = msg.get_srcSystem()
                mission_handler.target_component = msg.get_srcComponent()

                if not heartbeat_received:
                    heartbeat_received = True
                    last_version_req_time = time.time()
                    print(f"Autopilot Heartbeat received from Sys {msg.get_srcSystem()}:{msg.get_srcComponent()}! Connected to {detected_fc_hardware}.")
                    # Request Autopilot Version & Capabilities (Msg 148)
                    try:
                        connection.mav.command_long_send(
                            connection.target_system, connection.target_component,
                            mavutil.mavlink.MAV_CMD_REQUEST_AUTOPILOT_CAPABILITIES, 0,
                            1, 0, 0, 0, 0, 0, 0
                        )
                        connection.mav.command_long_send(
                            connection.target_system, connection.target_component,
                            mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE, 0,
                            mavutil.mavlink.MAVLINK_MSG_ID_AUTOPILOT_VERSION,
                            0, 0, 0, 0, 0, 0
                        )
                    except Exception as e:
                        pass
                else:
                    # Periodically re-query Autopilot Version if hardware identity is not yet fully resolved
                    if not is_network_sitl and detected_fc_hardware in ('Hardware FC', 'Unknown FC'):
                        now_t = time.time()
                        if now_t - last_version_req_time > 3.0:
                            last_version_req_time = now_t
                            try:
                                connection.mav.command_long_send(
                                    connection.target_system, connection.target_component,
                                    mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE, 0,
                                    mavutil.mavlink.MAVLINK_MSG_ID_AUTOPILOT_VERSION,
                                    0, 0, 0, 0, 0, 0
                                )
                            except Exception:
                                pass
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
                    # Explicitly request NAV_CONTROLLER_OUTPUT (Msg 62) at 5Hz
                    connection.mav.command_long_send(
                        connection.target_system, connection.target_component,
                        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                        62, 200000, 0, 0, 0, 0, 0
                    )
                    # Explicitly request HOME_POSITION (Msg 242) at 1Hz
                    connection.mav.command_long_send(
                        connection.target_system, connection.target_component,
                        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                        242, 1000000, 0, 0, 0, 0, 0
                    )
                    # Explicitly request ESC_TELEMETRY_1_TO_4 (Msg 11030) at 10Hz
                    connection.mav.command_long_send(
                        connection.target_system, connection.target_component,
                        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                        11030, 100000, 0, 0, 0, 0, 0
                    )
                    # Explicitly request ESC_TELEMETRY_5_TO_8 (Msg 11031) at 10Hz (Fixed-wing plane AUX/motor channels)
                    connection.mav.command_long_send(
                        connection.target_system, connection.target_component,
                        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                        11031, 100000, 0, 0, 0, 0, 0
                    )
                    # Explicitly request ESC_STATUS (Msg 291) at 10Hz
                    connection.mav.command_long_send(
                        connection.target_system, connection.target_component,
                        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                        291, 100000, 0, 0, 0, 0, 0
                    )
                    # Explicitly request SERVO_OUTPUT_RAW (Msg 36) at 20Hz (Servo/Motor PWM monitoring)
                    connection.mav.command_long_send(
                        connection.target_system, connection.target_component,
                        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                        36, 50000, 0, 0, 0, 0, 0
                    )
                    # Explicitly request SYS_STATUS (Msg 1) at 10Hz (Live battery volts & amps)
                    connection.mav.command_long_send(
                        connection.target_system, connection.target_component,
                        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                        1, 100000, 0, 0, 0, 0, 0
                    )
                    # Explicitly request BATTERY_STATUS (Msg 147) at 5Hz
                    connection.mav.command_long_send(
                        connection.target_system, connection.target_component,
                        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                        147, 200000, 0, 0, 0, 0, 0
                    )
                    connection.mav.request_data_stream_send(connection.target_system, connection.target_component, mavutil.mavlink.MAV_DATA_STREAM_EXTRA3, 5, 1)

                    # Request Battery Capacity and Cell Count parameters
                    try:
                        connection.mav.param_request_read_send(
                            connection.target_system, connection.target_component,
                            b'BATT_CAPACITY', -1
                        )
                        connection.mav.param_request_read_send(
                            connection.target_system, connection.target_component,
                            b'BATT_SER_CELLS', -1
                        )
                    except Exception:
                        pass

                    # Trigger initial mission download from vehicle
                    mission_handler.start_fetch()

            data = {"type": msg.get_type()}
            if msg.get_type() == 'HEARTBEAT':
                # Decode Ardupilot mode strings safely
                mode_str = mavutil.mode_string_v10(msg)
                if mode_str and not mode_str.startswith("Mode("):
                    data['mode'] = mode_str
                else:
                    data['mode'] = getattr(msg, 'flight_mode', 'MANUAL')

                is_armed = bool(getattr(msg, 'base_mode', 0) & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                data['armed'] = is_armed
                data['base_mode'] = getattr(msg, 'base_mode', 0)
                data['system_status'] = getattr(msg, 'system_status', 0)

                if msg.type == mavutil.mavlink.MAV_TYPE_FIXED_WING or msg.type in [19, 20, 21, 22, 23, 24, 25]:
                    data['firmware'] = detected_firmware if detected_firmware else 'ArduPlane'
                elif msg.type in [mavutil.mavlink.MAV_TYPE_QUADROTOR, mavutil.mavlink.MAV_TYPE_HEXAROTOR, mavutil.mavlink.MAV_TYPE_OCTOROTOR, mavutil.mavlink.MAV_TYPE_TRICOPTER, mavutil.mavlink.MAV_TYPE_HELICOPTER]:
                    data['firmware'] = 'ArduCopter'
                elif msg.type in [mavutil.mavlink.MAV_TYPE_GROUND_ROVER, mavutil.mavlink.MAV_TYPE_SURFACE_BOAT]:
                    data['firmware'] = 'Rover'
                elif msg.type == mavutil.mavlink.MAV_TYPE_SUBMARINE:
                    data['firmware'] = 'ArduSub'
                else:
                    data['firmware'] = 'ArduPilot'
                data['fc_hardware'] = detected_fc_hardware
                cached_heartbeat = data
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
                data['vz'] = -getattr(msg, 'vz', 0.0) # Vertical climb rate in m/s (NED Down inverted to Up)
            elif msg.get_type() == 'GLOBAL_POSITION_INT':
                data['lat'] = msg.lat / 1e7
                data['lon'] = msg.lon / 1e7
                data['alt'] = msg.alt
                data['relative_alt'] = msg.relative_alt
                data['hdg'] = getattr(msg, 'hdg', 0) / 100.0
                data['vz'] = -getattr(msg, 'vz', 0.0) / 100.0 # Convert cm/s Down to m/s Up
            elif msg.get_type() == 'VFR_HUD':
                data['airspeed'] = msg.airspeed
                data['groundspeed'] = msg.groundspeed
                data['heading'] = getattr(msg, 'heading', None)
                data['climb'] = getattr(msg, 'climb', 0.0)
                data['throttle'] = int(getattr(msg, 'throttle', 0))
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
            elif msg.get_type() == 'HOME_POSITION':
                data['home_lat'] = msg.latitude / 1e7
                data['home_lon'] = msg.longitude / 1e7
                data['home_alt'] = msg.altitude / 1000.0
                cached_home_position = {
                    "type": "HOME_POSITION",
                    "home_lat": data['home_lat'],
                    "home_lon": data['home_lon'],
                    "home_alt": data['home_alt']
                }
            elif msg.get_type() == 'AUTOPILOT_VERSION':
                sw_ver = getattr(msg, 'flight_sw_version', 0)
                if sw_ver:
                    maj = (sw_ver >> 24) & 0xFF
                    min_v = (sw_ver >> 16) & 0xFF
                    pat = (sw_ver >> 8) & 0xFF
                    t_suffix = {0: '-dev', 64: '-alpha', 128: '-beta', 192: '-rc'}.get(sw_ver & 0xFF, '')
                    detected_firmware = f"ArduPlane V{maj}.{min_v}.{pat}{t_suffix}"
                    print(f"[FC Info] Autopilot Version detected: {detected_firmware}")
                vendor_id = getattr(msg, 'vendor_id', 0)
                product_id = getattr(msg, 'product_id', 0)
                board_ver = getattr(msg, 'board_version', 0)
                resolved = resolve_board_name(board_ver, vendor_id, product_id, is_network_sitl)
                if resolved and resolved != 'Hardware FC':
                    detected_fc_hardware = resolved
                    print(f"[FC Info] Autopilot Hardware resolved: {detected_fc_hardware} (board_version={board_ver})")
                elif vendor_id == 0 and product_id == 0 and board_ver == 0 and is_network_sitl:
                    detected_fc_hardware = "SITL"
                data['type'] = 'FC_INFO'
                data['fc_hardware'] = detected_fc_hardware
                data['firmware'] = detected_firmware

                if cached_heartbeat:
                    cached_heartbeat['fc_hardware'] = detected_fc_hardware
                    cached_heartbeat['firmware'] = detected_firmware

                if clients:
                    fc_json = json.dumps({
                        "type": "FC_INFO",
                        "fc_hardware": detected_fc_hardware,
                        "firmware": detected_firmware
                    })
                    for c in list(clients):
                        try:
                            await c.send(fc_json)
                        except Exception:
                            pass

            elif msg.get_type() == 'STATUSTEXT':
                raw_text = getattr(msg, 'text', '')
                if isinstance(raw_text, bytes):
                    raw_text = raw_text.decode('utf-8', errors='ignore')
                clean_text = str(raw_text).strip('\x00').strip()

                # Detect firmware version banner, e.g. 'ArduPlane V4.6.3 (3fc7011a)'
                m_fw = re.match(r'^(Ardu[A-Za-z]+)\s+V?([0-9]+\.[0-9]+(?:\.[0-9]+)?(?:-[A-Za-z0-9]+)?)', clean_text, re.IGNORECASE)
                if m_fw:
                    detected_firmware = f"{m_fw.group(1)} V{m_fw.group(2)}"
                    print(f"[FC Info] Firmware Banner detected: {detected_firmware}")
                    if cached_heartbeat:
                        cached_heartbeat['firmware'] = detected_firmware

                # Detect FC hardware board name, e.g. 'SpeedyBeeF405WING 003C0028...' or 'SITL 00000000'
                m_board = re.match(r'^([A-Za-z0-9_\-]+)\s+[0-9A-Fa-f]{8}\s+[0-9A-Fa-f]{8}', clean_text)
                if m_board:
                    b_name = m_board.group(1)
                    if b_name.upper() == 'SITL':
                        detected_fc_hardware = 'SITL'
                    elif not b_name.lower().startswith(('imu', 'rcout', 'ekf', 'baro', 'gps')):
                        detected_fc_hardware = format_fc_board_name(b_name)
                    print(f"[FC Info] Hardware Board detected from boot banner: {detected_fc_hardware}")
                    if cached_heartbeat:
                        cached_heartbeat['fc_hardware'] = detected_fc_hardware
                    if clients:
                        fc_json = json.dumps({
                            "type": "FC_INFO",
                            "fc_hardware": detected_fc_hardware,
                            "firmware": detected_firmware
                        })
                        for c in list(clients):
                            try:
                                await c.send(fc_json)
                            except Exception:
                                pass
                data['type'] = 'STATUSTEXT'
                data['severity'] = int(getattr(msg, 'severity', 6))
                data['text'] = clean_text
                data['timestamp'] = time.time()
                cached_statustext_messages.append({
                    "type": "STATUSTEXT",
                    "severity": data['severity'],
                    "text": clean_text,
                    "timestamp": data['timestamp']
                })
                if len(cached_statustext_messages) > 100:
                    cached_statustext_messages.pop(0)
                # Auto-detect mission update events reported via STATUSTEXT
                lower_txt = clean_text.lower()
                if "flight plan received" in lower_txt or ("loaded " in lower_txt and "waypoint" in lower_txt) or "mission reset" in lower_txt:
                    print(f"[Mission] Detected vehicle mission status event: '{clean_text}'. Syncing...")
                    mission_handler.start_fetch(force=True)
            elif msg.get_type() in ('ESC_TELEMETRY_1_TO_4', 'ESC_TELEMETRY_5_TO_8', 'ESC_TELEMETRY_9_TO_12'):
                data['type'] = 'ESC_TELEMETRY'
                offset = 0
                if msg.get_type() == 'ESC_TELEMETRY_5_TO_8':
                    offset = 4
                elif msg.get_type() == 'ESC_TELEMETRY_9_TO_12':
                    offset = 8
                data['channel_offset'] = offset
                data['rpm'] = list(getattr(msg, 'rpm', [0, 0, 0, 0]))
                data['voltage'] = [round(v / 100.0, 2) for v in getattr(msg, 'voltage', [0, 0, 0, 0])]
                data['current'] = [round(c / 100.0, 2) for c in getattr(msg, 'current', [0, 0, 0, 0])]
                raw_temp = getattr(msg, 'temperature', [0, 0, 0, 0])
                data['temperature'] = [round(t / 100.0, 1) if t > 500 else float(t) for t in raw_temp]
                data['total_current'] = round(getattr(msg, 'total_current', 0) / 100.0, 2)
            elif msg.get_type() == 'ESC_STATUS':
                data['type'] = 'ESC_STATUS'
                data['index'] = getattr(msg, 'index', 0)
                data['rpm'] = list(getattr(msg, 'rpm', []))
                data['voltage'] = [round(v / 100.0, 2) for v in getattr(msg, 'voltage', [])]
                data['current'] = [round(c / 100.0, 2) for c in getattr(msg, 'current', [])]
            elif msg.get_type() == 'BATTERY_STATUS':
                data['type'] = 'BATTERY_STATUS'
                raw_cell_mv = getattr(msg, 'voltages', [])
                data['cell_voltages'] = [round(v / 1000.0, 2) for v in raw_cell_mv if 0 < v < 65000]
                data['current_battery'] = round(getattr(msg, 'current_battery', 0) / 100.0, 2)
                data['current_consumed'] = getattr(msg, 'current_consumed', 0)
                data['battery_remaining'] = getattr(msg, 'battery_remaining', -1)
            elif msg.get_type() == 'SYS_STATUS':
                data['type'] = 'SYS_STATUS'
                data['voltage_battery'] = round(getattr(msg, 'voltage_battery', 0) / 1000.0, 2)
                data['current_battery'] = round(getattr(msg, 'current_battery', 0) / 100.0, 2)
                data['battery_remaining'] = getattr(msg, 'battery_remaining', -1)
            elif msg.get_type() == 'SIMSTATE':
                data['sim_lat'] = getattr(msg, 'lat', 0) / 1e7
                data['sim_lon'] = getattr(msg, 'lng', 0) / 1e7
            elif msg.get_type() == 'PARAM_VALUE':
                param_id = getattr(msg, 'param_id', '')
                if isinstance(param_id, bytes):
                    param_id = param_id.decode('utf-8', errors='ignore').strip('\x00')
                data['param_id'] = str(param_id)
                data['param_value'] = float(getattr(msg, 'param_value', 0.0))
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
        # Deliver cached FC info (hardware and firmware version) to newly connected client
        try:
            await websocket.send(json.dumps({
                "type": "FC_INFO",
                "fc_hardware": detected_fc_hardware,
                "firmware": detected_firmware
            }))
        except Exception:
            pass

        # Deliver cached heartbeat (arm status, mode, firmware) to newly connected client immediately
        if cached_heartbeat:
            try:
                await websocket.send(json.dumps(cached_heartbeat))
            except Exception as e:
                print(f"[Server] Error sending cached heartbeat: {e}")

        # Deliver cached home position to newly connected client immediately
        if cached_home_position:
            try:
                await websocket.send(json.dumps(cached_home_position))
            except Exception as e:
                print(f"[Server] Error sending cached home position: {e}")

        # Deliver cached status text messages to newly connected client immediately
        if cached_statustext_messages:
            try:
                await websocket.send(json.dumps({
                    "type": "STATUSTEXT_HISTORY",
                    "messages": cached_statustext_messages
                }))
            except Exception as e:
                print(f"[Server] Error sending cached status messages: {e}")

        # Deliver cached mission waypoints to newly connected client immediately
        if mission_handler.waypoints:
            valid_wps = [w for w in mission_handler.waypoints if w is not None]
            if valid_wps:
                try:
                    await websocket.send(json.dumps({
                        "type": "MISSION_WAYPOINTS",
                        "waypoints": valid_wps,
                        "count": len(valid_wps),
                        "current_seq": mission_handler.current_seq
                    }))
                except Exception as e:
                    print(f"[Mission] Error sending cached waypoints: {e}")
        # Proactively trigger live vehicle sync on client connect
        if heartbeat_received and not mission_handler.is_fetching:
            mission_handler.start_fetch(force=False)

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
                elif action == "fetch_waypoints":
                    force = bool(cmd.get("force", False))
                    # 1. Immediately send cached waypoints so the frontend has instantaneous display
                    valid_wps = [w for w in mission_handler.waypoints if w is not None] if mission_handler.waypoints else []
                    if valid_wps:
                        try:
                            await websocket.send(json.dumps({
                                "type": "MISSION_WAYPOINTS",
                                "waypoints": valid_wps,
                                "count": len(valid_wps),
                                "current_seq": mission_handler.current_seq
                            }))
                        except Exception:
                            pass
                    # 2. ALWAYS initiate a live fetch from the vehicle so newly uploaded/modified waypoints are updated
                    ok = mission_handler.start_fetch(force=True)
                    print(f"[Mission] Client requested waypoint fetch (initiated live vehicle sync: {ok})")
                elif action == "set_current_waypoint":
                    seq = int(cmd.get("seq", 0))
                    mission_handler.set_current(seq)
                    print(f"[Mission] Client requested set current waypoint seq {seq}")
            except Exception as e:
                print(f"[Server] Error processing client message: {e}")
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        clients.discard(websocket)

tile_cache_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tile_cache'))
os.makedirs(tile_cache_dir, exist_ok=True)
dem_cache_dir = os.path.abspath(os.path.join(tile_cache_dir, 'dem'))
os.makedirs(dem_cache_dir, exist_ok=True)

precache_state = {
    "is_downloading": False,
    "progress_pct": 0,
    "downloaded": 0,
    "cached": 0,
    "failed": 0,
    "total": 0,
    "status": "Idle"
}

# OpenSky In-Memory Cache (10-second TTL to adhere to OpenSky rate limits)
opensky_cache = {
    'timestamp': 0,
    'last_lat': None,
    'last_lon': None,
    'data': []
}

def fetch_tile(z, x, y, provider='esri', lyrs='s'):
    try:
        if provider == 'esri':
            url = f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
        elif provider == 'google_hybrid':
            mt = abs(x + y) % 4
            url = f"https://mt{mt}.google.com/vt/lyrs=y&x={x}&y={y}&z={z}"
        else: # google satellite
            mt = abs(x + y) % 4
            url = f"https://mt{mt}.google.com/vt/lyrs={lyrs}&x={x}&y={y}&z={z}"
            
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                return resp.read()
    except Exception:
        return None
    return None

def fetch_dem_tile(z, x, y):
    try:
        url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req, timeout=5) as resp:
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

def sanitize_preset_folder(preset_name):
    if not preset_name or not str(preset_name).strip():
        return "default"
    clean = re.sub(r'[^a-zA-Z0-9_\-]+', '_', str(preset_name).strip()).strip('_')
    return clean if clean else "default"

def run_precache_worker(lat, lon, radius_km, zoom_levels, provider='esri', preset='default'):
    global precache_state
    precache_state["is_downloading"] = True
    precache_state["status"] = "Calculating tiles..."
    
    preset_folder = sanitize_preset_folder(preset)
    target_cache_dir = os.path.join(tile_cache_dir, preset_folder)
    os.makedirs(target_cache_dir, exist_ok=True)
    
    all_tiles = []
    for z in zoom_levels:
        all_tiles.extend(get_tiles_for_radius(lat, lon, radius_km, z))

    total = len(all_tiles)
    precache_state["total"] = total
    precache_state["downloaded"] = 0
    precache_state["cached"] = 0
    precache_state["failed"] = 0
    precache_state["status"] = f"Downloading {total} tiles for {preset_folder}..."

    def proc_tile(tile_info):
        z, x, y = tile_info
        suffix = f"_{provider}" if provider != 'google' else ""
        tile_filename = f"{z}_{x}_{y}{suffix}.jpg"
        tile_path = os.path.join(target_cache_dir, tile_filename)
        root_tile_path = os.path.join(tile_cache_dir, tile_filename)

        if os.path.exists(tile_path) and os.path.getsize(tile_path) > 100:
            return 'CACHED'
        if os.path.exists(root_tile_path) and os.path.getsize(root_tile_path) > 100:
            try:
                shutil.copy2(root_tile_path, tile_path)
                return 'CACHED'
            except Exception:
                pass

        # Also pre-cache DEM elevation tile for 3D terrain
        try:
            dem_z = min(z, 15)
            zoom_diff = z - dem_z
            dem_x = x >> zoom_diff
            dem_y = y >> zoom_diff
            dem_file = os.path.join(dem_cache_dir, f"{dem_z}_{dem_x}_{dem_y}.png")
            if not os.path.exists(dem_file) or os.path.getsize(dem_file) <= 100:
                dem_bytes = fetch_dem_tile(dem_z, dem_x, dem_y)
                if dem_bytes and len(dem_bytes) > 100:
                    with open(dem_file, 'wb') as df:
                        df.write(dem_bytes)
        except Exception:
            pass

        data = fetch_tile(z, x, y, provider=provider)
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
    precache_state["status"] = f"Complete: {precache_state['downloaded'] + precache_state['cached']}/{total} tiles ready in {preset_folder}/"

def start_http_server():
    vis_dir = os.path.join(os.path.dirname(__file__), '..', 'visualizer')
    os.chdir(vis_dir)
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def end_headers(self):
            if not getattr(self, '_is_tile', False):
                self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
                self.send_header('Pragma', 'no-cache')
                self.send_header('Expires', '0')
            self.send_header('Access-Control-Allow-Origin', '*')
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
                    provider = query_params.get('provider', ['esri'])[0]
                    preset = query_params.get('preset', ['default'])[0]
                    lyrs = query_params.get('lyrs', ['s'])[0]
                    parts = clean_path.split('/')
                    if len(parts) >= 5:
                        z = parts[2]
                        x = parts[3]
                        y = parts[4].split('.')[0]
                        suffix = f"_{provider}" if provider != 'google' else (f"_{lyrs}" if lyrs != 's' else "")
                        tile_filename = f"{z}_{x}_{y}{suffix}.jpg"

                        preset_folder = sanitize_preset_folder(preset)
                        preset_dir = os.path.join(tile_cache_dir, preset_folder)
                        os.makedirs(preset_dir, exist_ok=True)
                        preset_tile_file = os.path.join(preset_dir, tile_filename)
                        root_tile_file = os.path.join(tile_cache_dir, tile_filename)

                        target_file = None
                        if os.path.exists(preset_tile_file) and os.path.getsize(preset_tile_file) > 100:
                            target_file = preset_tile_file
                        elif os.path.exists(root_tile_file) and os.path.getsize(root_tile_file) > 100:
                            target_file = root_tile_file

                        if target_file:
                            with open(target_file, 'rb') as f:
                                data = f.read()
                            self.send_response(200)
                            self.send_header('Content-Type', 'image/jpeg')
                            self.send_header('Content-Length', str(len(data)))
                            self.send_header('Cache-Control', 'public, max-age=31536000')
                            self.end_headers()
                            self.wfile.write(data)
                            return
                        elif mode != 'offline':
                            data = fetch_tile(int(z), int(x), int(y), provider=provider, lyrs=lyrs)
                            if data:
                                try:
                                    with open(preset_tile_file, 'wb') as f:
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

            # 1b. DEM Elevation Tile proxy and disk caching: /dem/<z>/<x>/<y>.png
            elif self.path.startswith('/dem/'):
                self._is_tile = True
                try:
                    clean_path = self.path.split('?')[0]
                    parts = clean_path.split('/')
                    if len(parts) >= 5:
                        z = int(parts[2])
                        x = int(parts[3])
                        y = int(parts[4].split('.')[0])

                        # Terrarium DEM tiles natively exist up to zoom 15
                        dem_z = min(z, 15)
                        zoom_diff = z - dem_z
                        dem_x = x >> zoom_diff
                        dem_y = y >> zoom_diff

                        dem_filename = f"{dem_z}_{dem_x}_{dem_y}.png"
                        dem_file = os.path.join(dem_cache_dir, dem_filename)

                        if os.path.exists(dem_file) and os.path.getsize(dem_file) > 100:
                            with open(dem_file, 'rb') as f:
                                data = f.read()
                            self.send_response(200)
                            self.send_header('Content-Type', 'image/png')
                            self.send_header('Content-Length', str(len(data)))
                            self.send_header('Cache-Control', 'public, max-age=31536000')
                            self.end_headers()
                            self.wfile.write(data)
                            return
                        else:
                            data = fetch_dem_tile(dem_z, dem_x, dem_y)
                            if data and len(data) > 100:
                                try:
                                    with open(dem_file, 'wb') as f:
                                        f.write(data)
                                except Exception: pass
                                self.send_response(200)
                                self.send_header('Content-Type', 'image/png')
                                self.send_header('Content-Length', str(len(data)))
                                self.send_header('Cache-Control', 'public, max-age=31536000')
                                self.end_headers()
                                self.wfile.write(data)
                                return
                except Exception:
                    pass
                self.send_error(404, "DEM Tile not found")
                return

            # 2. Clear cache endpoint: /api/clear_cache?preset=...
            elif self.path.startswith('/api/clear_cache'):
                try:
                    query_str = self.path.split('?')[1] if '?' in self.path else ''
                    query_params = urllib.parse.parse_qs(query_str)
                    preset = query_params.get('preset', [''])[0]
                    cleared_count = 0

                    if preset and preset != 'all':
                        preset_folder = sanitize_preset_folder(preset)
                        target_dir = os.path.join(tile_cache_dir, preset_folder)
                        if os.path.exists(target_dir):
                            for f in os.listdir(target_dir):
                                if f.endswith('.jpg'):
                                    try:
                                        os.remove(os.path.join(target_dir, f))
                                        cleared_count += 1
                                    except Exception: pass
                    else:
                        for root, dirs, files in os.walk(tile_cache_dir):
                            for f in files:
                                if f.endswith('.jpg') or f.endswith('.png'):
                                    try:
                                        os.remove(os.path.join(root, f))
                                        cleared_count += 1
                                    except Exception: pass

                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "cleared", "count": cleared_count}).encode('utf-8'))
                    return
                except Exception as e:
                    self.send_error(500, str(e))
                    return

            # 3. Cache status API: /api/cache_status?preset=...
            elif self.path.startswith('/api/cache_status'):
                try:
                    query_str = self.path.split('?')[1] if '?' in self.path else ''
                    query_params = urllib.parse.parse_qs(query_str)
                    preset = query_params.get('preset', ['default'])[0]
                    preset_folder = sanitize_preset_folder(preset)
                    target_dir = os.path.join(tile_cache_dir, preset_folder)

                    preset_files = [f for f in os.listdir(target_dir) if f.endswith('.jpg')] if os.path.exists(target_dir) else []
                    preset_mb = sum(os.path.getsize(os.path.join(target_dir, f)) for f in preset_files) / (1024 * 1024) if preset_files else 0.0

                    total_files_count = 0
                    total_bytes = 0
                    for root, dirs, files in os.walk(tile_cache_dir):
                        for f in files:
                            if f.endswith('.jpg'):
                                total_files_count += 1
                                try:
                                    total_bytes += os.path.getsize(os.path.join(root, f))
                                except Exception: pass

                    total_mb = total_bytes / (1024 * 1024)

                    resp = {
                        "preset_folder": preset_folder,
                        "preset_dir": f"tile_cache/{preset_folder}/",
                        "cached_count": len(preset_files),
                        "cached_mb": round(preset_mb, 2),
                        "total_cached_count": total_files_count,
                        "total_cached_mb": round(total_mb, 2),
                        "is_downloading": precache_state["is_downloading"],
                        "progress_pct": precache_state["progress_pct"],
                        "downloaded": precache_state["downloaded"],
                        "cached": precache_state["cached"],
                        "failed": precache_state["failed"],
                        "total": precache_state["total"],
                        "status": precache_state["status"]
                    }
                except Exception:
                    resp = {
                        "preset_folder": "default",
                        "preset_dir": "tile_cache/default/",
                        "cached_count": 0,
                        "cached_mb": 0.0,
                        "total_cached_count": 0,
                        "total_cached_mb": 0.0,
                        "is_downloading": False,
                        "progress_pct": 0,
                        "downloaded": 0,
                        "cached": 0,
                        "failed": 0,
                        "total": 0,
                        "status": "Idle"
                    }

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(resp).encode('utf-8'))
                return

            # 4. Redirect root and index to sharkee_hud.html
            if self.path in ('/', '/index.html'):
                self.send_response(302)
                self.send_header('Location', '/sharkee_hud.html')
                self.end_headers()
                return

            # 5. OpenSky ADS-B Radar proxy
            elif self.path.startswith('/api/opensky'):
                parsed = urllib.parse.urlparse(self.path)
                params = urllib.parse.parse_qs(parsed.query)
                try:
                    lat = float(params.get('lat', [8.3113])[0])
                    lon = float(params.get('lon', [77.3077])[0])
                except (ValueError, TypeError):
                    lat, lon = 8.3113, 77.3077

                now = time.time()
                cache_valid = (
                    (now - opensky_cache['timestamp'] < 10.0) and
                    opensky_cache['last_lat'] is not None and
                    abs(opensky_cache['last_lat'] - lat) < 0.1 and
                    abs(opensky_cache['last_lon'] - lon) < 0.1
                )

                if cache_valid:
                    payload = {'status': 'ok', 'source': 'cache', 'states': opensky_cache['data']}
                else:
                    lamin = lat - 0.45
                    lamax = lat + 0.45
                    lomin = lon - 0.45
                    lomax = lon + 0.45
                    url = f"https://opensky-network.org/api/states/all?lamin={lamin:.4f}&lomin={lomin:.4f}&lamax={lamax:.4f}&lomax={lomax:.4f}"
                    req = urllib.request.Request(url, headers={'User-Agent': 'KarshakAvionics-HUD/1.0'})
                    try:
                        with urllib.request.urlopen(req, timeout=4.5) as resp_os:
                            raw = json.loads(resp_os.read().decode('utf-8'))
                            states = raw.get('states') or []
                            opensky_cache['timestamp'] = now
                            opensky_cache['last_lat'] = lat
                            opensky_cache['last_lon'] = lon
                            opensky_cache['data'] = states
                            payload = {'status': 'ok', 'source': 'live', 'states': states}
                    except Exception as e:
                        payload = {'status': 'error', 'message': str(e), 'states': opensky_cache['data']}

                body = json.dumps(payload).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
                self.send_header('Access-Control-Allow-Headers', '*')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
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
                    provider = data.get('provider', 'esri')
                    preset = data.get('preset', 'default')
                    if not precache_state["is_downloading"]:
                        threading.Thread(target=run_precache_worker, args=(lat, lon, radius, zooms, provider, preset), daemon=True).start()
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
    parser.add_argument("--connect", "--mavlink", "-c", default="udpin:127.0.0.1:14551", help="MAVLink target (e.g. udpin:127.0.0.1:14551, COM3:57600, udpin:0.0.0.0:14550)")
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
        print("[Visualizer] Opening browser tab at: http://127.0.0.1:8000/sharkee_hud.html\n")
        open_browser("http://127.0.0.1:8000/sharkee_hud.html")
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
                'http://127.0.0.1:8000/sharkee_hud.html', 
                js_api=api,
                width=1280, 
                height=720,
                background_color='#000000'
            )
            webview.start(icon=icon_path if os.path.exists(icon_path) else None)
        except Exception as e:
            print(f"\n[Notice] Native GUI window could not be started: {e}")
            print("[Server] Falling back to Headless Server Mode.")
            print("[Visualizer] Opening in your browser tab at: http://127.0.0.1:8000/sharkee_hud.html\n")
            open_browser("http://127.0.0.1:8000/sharkee_hud.html")
            try:
                while server_thread.is_alive():
                    server_thread.join(timeout=1.0)
            except KeyboardInterrupt:
                print("\nShutting down server.")



