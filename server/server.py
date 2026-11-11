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
import io
import logging
from PIL import Image
from pymavlink import mavutil

class WebSocketHandshakeFilter(logging.Filter):
    """
    Suppresses aborted or non-compliant handshake tracebacks (e.g., bare TCP port probes or early disconnects)
    from polluting the server telemetry console.
    """
    def filter(self, record):
        if record.exc_info:
            exc_type = record.exc_info[0]
            if exc_type and issubclass(exc_type, (EOFError, ConnectionResetError, BrokenPipeError)):
                return False
            if hasattr(websockets, 'exceptions') and issubclass(exc_type, (
                websockets.exceptions.InvalidMessage,
                websockets.exceptions.ConnectionClosedOK,
                websockets.exceptions.ConnectionClosedError
            )):
                return False
        msg = record.getMessage()
        if "opening handshake failed" in msg:
            return False
        return True

# Silence websockets handshake failure tracebacks for dropped or non-HTTP connections
logging.getLogger("websockets.server").addFilter(WebSocketHandshakeFilter())
logging.getLogger("websockets.protocol").addFilter(WebSocketHandshakeFilter())

# Server readiness synchronization events
http_server_ready_event = threading.Event()
ws_server_ready_event = threading.Event()

try:
    import requests
    from requests.adapters import HTTPAdapter
    _has_requests = True
    tile_http_session = requests.Session()
    _adapter = HTTPAdapter(pool_connections=35, pool_maxsize=70, max_retries=1)
    tile_http_session.mount('https://', _adapter)
    tile_http_session.mount('http://', _adapter)
    tile_http_session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
except ImportError:
    _has_requests = False
    tile_http_session = None

# Ensure current directory is in sys.path for sibling module imports without triggering circular import
_server_dir = os.path.dirname(os.path.abspath(__file__))
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

try:
    from board_types import (
        resolve_board_name,
        format_fc_board_name,
        resolve_board_from_text,
        resolve_fc_hardware_environment,
        get_connected_ardupilot_usb_devices,
    )
except ImportError:
    def resolve_board_name(*args, **kwargs): return "SITL"
    def format_fc_board_name(name): return name
    def resolve_board_from_text(text): return None
    def resolve_fc_hardware_environment(*args, **kwargs): return None, "unresolved"
    def get_connected_ardupilot_usb_devices(): return []

def check_port_listening(host, port, timeout=0.25):
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False

def normalize_mavlink_target(raw_target, default_baud=115200):
    if not raw_target:
        return 'udpin:0.0.0.0:14550', default_baud
    target = str(raw_target).strip()
    baud = default_baud

    # 1. Normalize pure port numbers or leading colon, e.g. '14550' or ':14550'
    if target.isdigit():
        return f'udpin:0.0.0.0:{target}', baud
    if target.startswith(':') and target[1:].isdigit():
        return f'udpin:0.0.0.0:{target[1:]}', baud

    # 2. Extract baud if formatted as COM3:115200 or /dev/ttyUSB0:115200 (not IP:port, udp:, or tcp:)
    if ':' in target and not target.startswith(('udp', 'tcp')) and not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+$', target):
        parts = target.split(':', 1)
        target = parts[0]
        try:
            baud = int(parts[1])
        except ValueError:
            pass
    
    # 3. Normalize IP:PORT without prefix (e.g., '0.0.0.0:14550' or '127.0.0.1:14550')
    if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+$', target):
        return f'udpin:{target}', baud

    # 4. Normalize udp:... (e.g. udp:14550 -> udpin:0.0.0.0:14550, udp:127.0.0.1:14550 -> udpin:127.0.0.1:14550)
    if target.startswith('udp:'):
        sub = target[4:]
        if sub.isdigit():
            return f'udpin:0.0.0.0:{sub}', baud
        elif ':' not in sub:
            return f'udpin:0.0.0.0:{sub}', baud
        else:
            return f'udpin:{sub}', baud

    if target.lower().startswith('com'):
        target = target.upper()

    return target, baud

def parse_mavlink_target():
    explicit = None
    baud = 115200

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg in ('--connect', '--mavlink', '-c') and i + 1 < len(sys.argv):
            explicit = sys.argv[i + 1]
            i += 2
            continue
        elif arg.startswith(('--connect=', '--mavlink=')):
            explicit = arg.split('=', 1)[1]
            i += 1
            continue
        elif arg in ('--udp', '-u') and i + 1 < len(sys.argv):
            udp_val = sys.argv[i + 1]
            explicit = f'udpin:0.0.0.0:{udp_val}' if udp_val.isdigit() else udp_val
            i += 2
            continue
        elif arg.startswith(('--udp=', '-u=')):
            udp_val = arg.split('=', 1)[1]
            explicit = f'udpin:0.0.0.0:{udp_val}' if udp_val.isdigit() else udp_val
            i += 1
            continue
        elif arg in ('--com',) and i + 1 < len(sys.argv):
            explicit = sys.argv[i + 1]
            i += 2
            continue
        elif arg.startswith('--com='):
            explicit = arg.split('=', 1)[1]
            i += 1
            continue
        elif arg in ('--baud', '-b') and i + 1 < len(sys.argv):
            try:
                baud = int(sys.argv[i + 1])
            except ValueError:
                pass
            i += 2
            continue
        elif arg.startswith(('--baud=', '-b=')):
            try:
                baud = int(arg.split('=', 1)[1])
            except ValueError:
                pass
            i += 1
            continue
        elif not arg.startswith('-') and explicit is None:
            explicit = arg
            i += 1
            continue
        i += 1

    if not explicit:
        explicit = os.environ.get('MAVLINK_URL')

    is_auto = False
    if explicit:
        target, target_baud = normalize_mavlink_target(explicit, baud)
        baud = target_baud
    else:
        is_auto = True
        # 1. Proactively detect active ArduPilot SITL instance on local TCP ports
        for candidate_port in (5762, 5763, 5760):
            if check_port_listening('127.0.0.1', candidate_port):
                target = f'tcp:127.0.0.1:{candidate_port}'
                print(f"[MAVLink Auto-Discovery] Detected active ArduPilot SITL instance on {target}")
                break
        else:
            # 2. Default to universal UDP telemetry receiver (UDP mirror from Mission Planner, QGC, or LAN broadcast).
            # Auto COM seizure is permanently disabled to prevent resource conflicts with Mission Planner.
            target = 'udpin:0.0.0.0:14550'
            print("[MAVLink Auto-Discovery] Auto COM scanning disabled. Defaulting to UDP receiver on udpin:0.0.0.0:14550")
            print("[MAVLink] (To connect to a serial COM port manually, use --com COMx or switch connection in the HUD UI)")

    return target, baud, is_auto

def create_mavlink_connection(target, baud=115200):
    if target.startswith(('udp', 'tcp')):
        print(f"[MAVLink] Connecting via network: {target}")
        return mavutil.mavlink_connection(target, source_system=254, source_component=190)
    else:
        print(f"[MAVLink] Connecting to serial port {target} at {baud} baud...")
        try:
            conn = mavutil.mavlink_connection(target, baud=baud, source_system=254, source_component=190)
            print(f"[MAVLink] Successfully opened serial port {target}.")
            return conn
        except PermissionError:
            print(f"[MAVLink] WARNING: Serial port {target} is locked by another process (e.g. Mission Planner).")
            print(f"[MAVLink] Falling back to UDP receiver udpin:0.0.0.0:14550 to keep visualizer online.")
            return mavutil.mavlink_connection('udpin:0.0.0.0:14550', source_system=254, source_component=190)
        except Exception as e:
            print(f"[MAVLink] WARNING: Could not open serial port {target}: {e}. Falling back to udpin:0.0.0.0:14550.")
            return mavutil.mavlink_connection('udpin:0.0.0.0:14550', source_system=254, source_component=190)

def is_ardupilot_sitl_target(dev_str):
    if not dev_str:
        return False
    d = str(dev_str).lower()
    return d.startswith('tcp') and any(h in d for h in ('127.0.0.1', 'localhost', '0.0.0.0')) and any(f':{p}' in d for p in (5760, 5762, 5763))

def send_hardware_identity_queries(conn):
    if not conn:
        return
    try:
        t_sys = getattr(conn, 'target_system', 1) or 1
        t_comp = getattr(conn, 'target_component', 1) or 1

        # 1. MAV_CMD_DO_SEND_BANNER (Command ID 42428) - Prompts ArduPilot to send startup text banner via STATUSTEXT
        try:
            conn.mav.command_long_send(
                t_sys, t_comp,
                42428, 0,
                0, 0, 0, 0, 0, 0, 0
            )
        except Exception:
            pass

        # 2. MAV_CMD_REQUEST_AUTOPILOT_CAPABILITIES (Command ID 520, param1=1)
        try:
            conn.mav.command_long_send(
                t_sys, t_comp,
                mavutil.mavlink.MAV_CMD_REQUEST_AUTOPILOT_CAPABILITIES, 0,
                1, 0, 0, 0, 0, 0, 0
            )
        except Exception:
            pass

        # 3. MAV_CMD_REQUEST_MESSAGE for AUTOPILOT_VERSION (Command ID 512, param1=148)
        try:
            conn.mav.command_long_send(
                t_sys, t_comp,
                mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE, 0,
                mavutil.mavlink.MAVLINK_MSG_ID_AUTOPILOT_VERSION,
                0, 0, 0, 0, 0, 0
            )
        except Exception:
            pass

        # 4. Standard AUTOPILOT_VERSION_REQUEST (Message 183)
        try:
            conn.mav.autopilot_version_request_send(t_sys, t_comp)
        except Exception:
            pass

        # 5. Request BRD_TYPE parameter (for PX4/Pixhawk boards)
        try:
            conn.mav.param_request_read_send(t_sys, t_comp, b'BRD_TYPE', -1)
        except Exception:
            pass
    except Exception:
        pass

def switch_mavlink_target(raw_target, req_baud=115200):
    global connection, MAVLINK_DEVICE, MAVLINK_BAUD, MAVLINK_URL, heartbeat_received, is_auto_target
    global is_network_sitl, detected_fc_hardware, last_version_req_time
    new_dev, new_baud = normalize_mavlink_target(raw_target, req_baud)
    print(f"[MAVLink] Switching MAVLink connection to {new_dev} (baud={new_baud})...")
    try:
        if new_dev.startswith(('udp', 'tcp')):
            new_conn = mavutil.mavlink_connection(new_dev, source_system=254, source_component=190)
        else:
            new_conn = mavutil.mavlink_connection(new_dev, baud=new_baud, source_system=254, source_component=190)

        try:
            connection.close()
        except Exception:
            pass

        connection = new_conn
        mission_handler.conn = connection
        MAVLINK_DEVICE = new_dev
        MAVLINK_BAUD = new_baud
        MAVLINK_URL = f'{new_dev}:{new_baud}' if not new_dev.startswith(('udp', 'tcp')) else new_dev
        heartbeat_received = False
        is_auto_target = False
        last_version_req_time = 0
        is_network_sitl = is_ardupilot_sitl_target(new_dev)
        if is_network_sitl:
            detected_fc_hardware = "SITL"
        else:
            env_board, env_reason = resolve_fc_hardware_environment(is_network_sitl=is_network_sitl)
            if env_board:
                detected_fc_hardware = env_board
                print(f"[FC Info] Hardware resolved from environment: {detected_fc_hardware} ({env_reason})")
            else:
                detected_fc_hardware = "Detecting FC..."
        print(f"[MAVLink] Successfully switched connection to {MAVLINK_URL}")
        return True, f"Connected to {MAVLINK_URL}"
    except Exception as e:
        print(f"[MAVLink] Error switching connection to {new_dev}: {e}")
        return False, str(e)

MAVLINK_DEVICE, MAVLINK_BAUD, is_auto_target = parse_mavlink_target()
MAVLINK_URL = f'{MAVLINK_DEVICE}:{MAVLINK_BAUD}' if not MAVLINK_DEVICE.startswith(('udp', 'tcp')) else MAVLINK_DEVICE
connection = create_mavlink_connection(MAVLINK_DEVICE, MAVLINK_BAUD)

clients = set()
heartbeat_received = False
is_network_sitl = is_ardupilot_sitl_target(MAVLINK_DEVICE)
if is_network_sitl:
    detected_fc_hardware = "SITL"
else:
    env_board, env_reason = resolve_fc_hardware_environment(is_network_sitl=is_network_sitl)
    if env_board:
        detected_fc_hardware = env_board
        print(f"[FC Info] Hardware resolved from environment: {detected_fc_hardware} ({env_reason})")
    else:
        detected_fc_hardware = "Detecting FC..."
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

                # Fast graceful resolution for 1-item missions (Home seq 0 in ArduPilot)
                if self.expected_count == 1 and missing == [0] and self.retries >= 1:
                    h_lat = None
                    h_lon = None
                    h_alt = 0.0
                    if cached_home_position:
                        h_lat = cached_home_position.get('home_lat') or cached_home_position.get('lat')
                        h_lon = cached_home_position.get('home_lon') or cached_home_position.get('lon')
                        h_alt = cached_home_position.get('home_alt') or cached_home_position.get('alt', 0.0)
                    elif hasattr(self, 'waypoints') and self.waypoints and len(self.waypoints) > 0:
                        h_lat = self.waypoints[0].get('lat')
                        h_lon = self.waypoints[0].get('lon')
                        h_alt = self.waypoints[0].get('alt', 0.0)

                    if h_lat and h_lon:
                        item = {
                            "seq": 0, "command": 16, "frame": 0,
                            "lat": h_lat, "lon": h_lon,
                            "alt": h_alt,
                            "param1": 0.0, "param2": 0.0, "param3": 0.0, "param4": 0.0,
                            "current": 0, "autocontinue": 1
                        }
                        self._pending_waypoints[0] = item
                        self.is_fetching = False
                        # If disk cache already has a rich flight plan, retain it!
                        if os.path.exists(self.cache_file):
                            try:
                                with open(self.cache_file, 'r', encoding='utf-8') as cf:
                                    existing = json.load(cf)
                                if isinstance(existing, list) and len(existing) > 1:
                                    print(f"[Mission] Vehicle reported only home waypoint (seq 0). Retaining rich mission ({len(existing)} WPs) from disk cache.")
                                    self.waypoints = existing
                                    return {
                                        "type": "MISSION_WAYPOINTS",
                                        "waypoints": existing,
                                        "count": len(existing),
                                        "current_seq": self.current_seq
                                    }
                            except Exception: pass
                        self.waypoints = [item]
                        return {
                            "type": "MISSION_WAYPOINTS",
                            "waypoints": [item],
                            "count": 1,
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
                    if valid_wps and len(valid_wps) > 1:
                        self.waypoints = valid_wps
                        return {
                            "type": "MISSION_WAYPOINTS",
                            "waypoints": valid_wps,
                            "count": len(valid_wps),
                            "current_seq": self.current_seq
                        }
                    elif os.path.exists(self.cache_file):
                        # Preserve existing cached waypoints on disk
                        try:
                            with open(self.cache_file, 'r', encoding='utf-8') as cf:
                                existing = json.load(cf)
                            if isinstance(existing, list) and len(existing) > 1:
                                print(f"[Mission] Retaining existing cached mission ({len(existing)} waypoints) from disk.")
                                self.waypoints = existing
                                return {
                                    "type": "MISSION_WAYPOINTS",
                                    "waypoints": existing,
                                    "count": len(existing),
                                    "current_seq": self.current_seq
                                }
                        except Exception: pass
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
    global heartbeat_received, cached_home_position, cached_statustext_messages, cached_heartbeat
    global detected_firmware, detected_fc_hardware, last_version_req_time, connection, MAVLINK_URL, MAVLINK_DEVICE, is_network_sitl
    print(f"Waiting for MAVLink heartbeat on {MAVLINK_URL}...")

    last_auto_scan_time = 0

    while True:
        # Proactive auto-scan if in auto mode targeting SITL and no heartbeat has been received
        now = time.time()
        if is_auto_target and not heartbeat_received and MAVLINK_DEVICE.startswith('tcp'):
            if last_auto_scan_time == 0:
                last_auto_scan_time = now
            elif now - last_auto_scan_time > 2.0:
                last_auto_scan_time = now
                found_port = None
                for candidate in (5762, 5763, 5760):
                    if check_port_listening('127.0.0.1', candidate):
                        found_port = candidate
                        break
                if found_port and MAVLINK_DEVICE != f'tcp:127.0.0.1:{found_port}':
                    try:
                        print(f"[MAVLink Auto-Discovery] Active SITL instance detected on tcp:127.0.0.1:{found_port}! Switching connection...")
                        try:
                            connection.close()
                        except Exception:
                            pass
                        new_conn = mavutil.mavlink_connection(f'tcp:127.0.0.1:{found_port}')
                        connection = new_conn
                        mission_handler.conn = connection
                        MAVLINK_DEVICE = f'tcp:127.0.0.1:{found_port}'
                        MAVLINK_URL = f'tcp:127.0.0.1:{found_port}'
                        is_network_sitl = True
                        detected_fc_hardware = "SITL"
                        heartbeat_received = False
                    except Exception as e:
                        print(f"[MAVLink Auto-Discovery] Error connecting to tcp:127.0.0.1:{found_port}: {e}")

        try:
            msg = connection.recv_match(
                type=['HEARTBEAT', 'ATTITUDE', 'AUTOPILOT_VERSION', 'SERVO_OUTPUT_RAW', 'LOCAL_POSITION_NED', 'VFR_HUD',
                      'ESC_TELEMETRY_1_TO_4', 'ESC_TELEMETRY_5_TO_8', 'ESC_TELEMETRY_9_TO_12', 'ESC_STATUS', 'BATTERY_STATUS', 'SYS_STATUS',
                      'GLOBAL_POSITION_INT', 'TERRAIN_REPORT', 'WIND', 'GPS_RAW_INT', 'SIMSTATE',
                      'ESTIMATOR_STATUS', 'MISSION_COUNT', 'MISSION_ITEM_INT', 'MISSION_ITEM',
                      'MISSION_CURRENT', 'MISSION_ITEM_REACHED', 'MISSION_ACK', 'NAV_CONTROLLER_OUTPUT', 'HOME_POSITION',
                      'STATUSTEXT', 'PARAM_VALUE'],
                blocking=False
            )
        except (ConnectionResetError, ConnectionError, BrokenPipeError, OSError):
            # If TCP socket was disconnected (e.g. SITL stopped or restarted), auto-reconnect
            if MAVLINK_DEVICE.startswith('tcp'):
                if heartbeat_received:
                    print(f"[MAVLink] Connection to {MAVLINK_URL} interrupted. Reconnecting in background...")
                    heartbeat_received = False
                    if clients:
                        stat_payload = json.dumps({
                            "type": "MAVLINK_STATUS",
                            "connected": False,
                            "url": MAVLINK_URL,
                            "fc_hardware": detected_fc_hardware
                        })
                        for c in list(clients):
                            try:
                                await c.send(stat_payload)
                            except Exception:
                                pass
                try:
                    connection.close()
                except Exception:
                    pass
                await asyncio.sleep(1.0)
                reconnect_target = 'tcp:127.0.0.1:5762' if check_port_listening('127.0.0.1', 5762) else ('tcp:127.0.0.1:5763' if check_port_listening('127.0.0.1', 5763) else None)
                if reconnect_target:
                    try:
                        connection = mavutil.mavlink_connection(reconnect_target)
                        mission_handler.conn = connection
                        MAVLINK_DEVICE = reconnect_target
                        MAVLINK_URL = reconnect_target
                        print(f"[MAVLink] Successfully reconnected to SITL on {MAVLINK_URL}")
                    except Exception:
                        pass
                continue
            await asyncio.sleep(0.01)
            continue
        except Exception:
            await asyncio.sleep(0.01)
            continue
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
                    if detected_fc_hardware in ('Detecting...', 'Detecting FC...', 'Hardware FC', 'Unknown FC', 'UDP Mirror', 'Searching...') and not is_network_sitl:
                        env_board, env_reason = resolve_fc_hardware_environment(is_network_sitl=is_network_sitl)
                        if env_board:
                            detected_fc_hardware = env_board
                            print(f"[FC Info] Hardware resolved from environment: {detected_fc_hardware} ({env_reason})")
                    print(f"Autopilot Heartbeat received from Sys {msg.get_srcSystem()}:{msg.get_srcComponent()}! Connected to {detected_fc_hardware}.")
                    if clients:
                        stat_payload = json.dumps({
                            "type": "MAVLINK_STATUS",
                            "connected": True,
                            "url": MAVLINK_URL,
                            "fc_hardware": detected_fc_hardware
                        })
                        for c in list(clients):
                            try:
                                await c.send(stat_payload)
                            except Exception:
                                pass
                    # Request Autopilot Version & Capabilities (Multi-pronged queries)
                    send_hardware_identity_queries(connection)

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

                    # Request Battery Capacity and Cell Count parameters, and Board Type
                    try:
                        connection.mav.param_request_read_send(
                            connection.target_system, connection.target_component,
                            b'BATT_CAPACITY', -1
                        )
                        connection.mav.param_request_read_send(
                            connection.target_system, connection.target_component,
                            b'BATT_SER_CELLS', -1
                        )
                        connection.mav.param_request_read_send(
                            connection.target_system, connection.target_component,
                            b'BRD_TYPE', -1
                        )
                    except Exception:
                        pass

                    # Trigger initial mission download from vehicle
                    mission_handler.start_fetch()
                else:
                    # Periodically re-query Autopilot Version and Hardware Board Banner if hardware identity is not yet fully resolved
                    UNRESOLVED_HARDWARE = ('Detecting...', 'Detecting FC...', 'Hardware FC', 'Unknown FC', 'UDP Mirror', 'Searching...')
                    if detected_fc_hardware in UNRESOLVED_HARDWARE:
                        now_t = time.time()
                        if now_t - last_version_req_time > 2.0:
                            last_version_req_time = now_t
                            if not is_network_sitl:
                                env_board, env_reason = resolve_fc_hardware_environment(is_network_sitl=is_network_sitl)
                                if env_board:
                                    detected_fc_hardware = env_board
                                    print(f"[FC Info] Hardware resolved from environment: {detected_fc_hardware} ({env_reason})")
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
                                                asyncio.create_task(c.send(fc_json))
                                            except Exception:
                                                pass
                            send_hardware_identity_queries(connection)

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
                if resolved and resolved not in ('Hardware FC', 'Unknown FC', 'Detecting FC...', 'Detecting...'):
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
                txt_board = resolve_board_from_text(clean_text)
                if txt_board and txt_board not in ('Hardware FC', 'Unknown FC', 'Detecting FC...', 'Detecting...'):
                    detected_fc_hardware = txt_board
                    print(f"[FC Info] Hardware Board detected from text: {detected_fc_hardware}")
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
                                asyncio.create_task(c.send(fc_json))
                            except Exception:
                                pass
                else:
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
                                    asyncio.create_task(c.send(fc_json))
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
                param_id_str = str(param_id).strip()
                param_val = float(getattr(msg, 'param_value', 0.0))
                data['param_id'] = param_id_str
                data['param_value'] = param_val

                if param_id_str.upper() == 'BRD_TYPE':
                    board_id = int(param_val)
                    resolved = resolve_board_name(board_id, is_network_sitl=is_network_sitl)
                    if resolved and resolved not in ('Hardware FC', 'Unknown FC', 'Detecting FC...', 'Detecting...'):
                        detected_fc_hardware = resolved
                        print(f"[FC Info] Resolved FC from BRD_TYPE={board_id}: {detected_fc_hardware}")
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
                                    asyncio.create_task(c.send(fc_json))
                                except Exception:
                                    pass
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

        # Deliver live connection link state
        try:
            await websocket.send(json.dumps({
                "type": "MAVLINK_STATUS",
                "connected": heartbeat_received,
                "url": MAVLINK_URL,
                "target": MAVLINK_DEVICE
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
                    try:
                        connection.mav.param_set_send(
                            target_sys,
                            target_comp,
                            param_id,
                            param_val,
                            mavutil.mavlink.MAV_PARAM_TYPE_REAL32
                        )
                    except (ConnectionResetError, ConnectionError, OSError):
                        pass
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
                    # 2. Initiate live fetch from vehicle (respecting force flag to avoid request thrashing)
                    ok = mission_handler.start_fetch(force=force)
                    print(f"[Mission] Client requested waypoint fetch (initiated live vehicle sync: {ok})")
                elif action == "set_current_waypoint":
                    seq = int(cmd.get("seq", 0))
                    mission_handler.set_current(seq)
                    print(f"[Mission] Client requested set current waypoint seq {seq}")
                elif action == "arm":
                    arm_val = 1 if cmd.get("value", True) else 0
                    target_sys = getattr(connection, 'target_system', 1) or 1
                    target_comp = getattr(connection, 'target_component', 1) or 1
                    try:
                        connection.mav.command_long_send(
                            target_sys,
                            target_comp,
                            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                            0,
                            arm_val, 0, 0, 0, 0, 0, 0
                        )
                    except (ConnectionResetError, ConnectionError, OSError):
                        pass
                    print(f"[MAVLink] Sent ARM_DISARM ({arm_val}) to Sys {target_sys}:{target_comp}")
                elif action == "set_mode":
                    mode_name = str(cmd.get("mode", "GUIDED")).upper()
                    try:
                        mode_mapping = connection.mode_mapping()
                        if mode_mapping and mode_name in mode_mapping:
                            mode_id = mode_mapping[mode_name]
                            connection.set_mode(mode_id)
                            print(f"[MAVLink] Set flight mode to {mode_name} (ID: {mode_id})")
                        else:
                            print(f"[MAVLink] Unknown flight mode: {mode_name}")
                    except Exception as me:
                        print(f"[MAVLink] Could not set flight mode {mode_name}: {me}")
                elif action == "takeoff":
                    alt = float(cmd.get("alt", 30.0))
                    target_sys = getattr(connection, 'target_system', 1) or 1
                    target_comp = getattr(connection, 'target_component', 1) or 1
                    try:
                        connection.mav.command_long_send(
                            target_sys,
                            target_comp,
                            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
                            0,
                            0, 0, 0, 0, 0, 0, alt
                        )
                    except (ConnectionResetError, ConnectionError, OSError):
                        pass
                    print(f"[MAVLink] Sent NAV_TAKEOFF (alt={alt}m) to Sys {target_sys}:{target_comp}")
                elif action == "connect_mavlink":
                    raw_target = cmd.get("target", "udpin:0.0.0.0:14550")
                    req_baud = int(cmd.get("baud", 115200))
                    success, res_msg = switch_mavlink_target(raw_target, req_baud)
                    status_payload = json.dumps({
                        "type": "MAVLINK_STATUS",
                        "connected": False,
                        "url": MAVLINK_URL,
                        "target": MAVLINK_DEVICE,
                        "baud": MAVLINK_BAUD,
                        "success": success,
                        "message": res_msg
                    })
                    for c in list(clients):
                        try:
                            await c.send(status_payload)
                        except Exception:
                            pass
                elif action == "get_serial_ports":
                    ports_list = []
                    try:
                        import serial.tools.list_ports
                        for p in serial.tools.list_ports.comports():
                            ports_list.append({
                                "device": p.device,
                                "description": p.description or p.device,
                                "manufacturer": p.manufacturer or ""
                            })
                    except Exception:
                        pass
                    try:
                        await websocket.send(json.dumps({
                            "type": "SERIAL_PORTS_LIST",
                            "ports": ports_list
                        }))
                    except Exception:
                        pass
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

is_online = True
last_connectivity_check = 0

def check_internet_reachability():
    global is_online, last_connectivity_check
    now = time.time()
    if now - last_connectivity_check < 4.0:
        return is_online
    last_connectivity_check = now
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.7)
        s.connect(('8.8.8.8', 53))
        s.close()
        is_online = True
    except Exception:
        is_online = False
    return is_online

def fetch_tile(z, x, y, provider='esri', lyrs='s'):
    if not check_internet_reachability():
        return None
    try:
        if provider == 'esri':
            if z > 18:
                # ESRI World Imagery terminates at Zoom 18 in this region. Seamlessly fallback to Google Satellite for sub-meter zoom!
                mt = abs(x + y) % 4
                url = f"https://mt{mt}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}"
            else:
                url = f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
        elif provider == 'google_hybrid':
            mt = abs(x + y) % 4
            url = f"https://mt{mt}.google.com/vt/lyrs=y&x={x}&y={y}&z={z}"
        else: # google satellite
            mt = abs(x + y) % 4
            url = f"https://mt{mt}.google.com/vt/lyrs={lyrs}&x={x}&y={y}&z={z}"
            
        if _has_requests and tile_http_session:
            resp = tile_http_session.get(url, timeout=3.5)
            if resp.status_code == 200:
                data = resp.content
                if len(data) == 2521 and provider == 'esri':
                    try:
                        mt = abs(x + y) % 4
                        g_url = f"https://mt{mt}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}"
                        g_resp = tile_http_session.get(g_url, timeout=3.0)
                        if g_resp.status_code == 200 and len(g_resp.content) > 100:
                            return g_resp.content
                    except Exception:
                        pass
                    return None
                return data
        else:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    data = resp.read()
                    if len(data) == 2521 and provider == 'esri':
                        try:
                            mt = abs(x + y) % 4
                            g_url = f"https://mt{mt}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}"
                            g_req = urllib.request.Request(g_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
                            with urllib.request.urlopen(g_req, timeout=5) as g_resp:
                                if g_resp.status == 200:
                                    return g_resp.read()
                        except Exception:
                            pass
                        return None
                    return data
    except Exception:
        return None
    return None

def fetch_dem_tile(z, x, y):
    if not check_internet_reachability():
        return None
    try:
        url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
        if _has_requests and tile_http_session:
            resp = tile_http_session.get(url, timeout=3.5)
            if resp.status_code == 200:
                return resp.content
        else:
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

def get_tiles_for_waypoints(waypoints, corridor_km, zoom):
    """
    Computes all unique (zoom, x, y) tiles covering a flight corridor buffer around
    a list of waypoints [{lat, lon}, ...].
    Interpolates along path segments so even 200 km diagonal routes only download
    the narrow corridor (e.g. 3 km buffer) instead of an oversized bounding box.
    """
    valid_pts = []
    for w in waypoints:
        if isinstance(w, dict):
            w_lat = float(w.get('lat', 0.0))
            w_lon = float(w.get('lon', 0.0))
            if abs(w_lat) > 0.001 and abs(w_lon) > 0.001:
                valid_pts.append((w_lat, w_lon))

    if not valid_pts:
        return []

    if len(valid_pts) == 1:
        return get_tiles_for_radius(valid_pts[0][0], valid_pts[0][1], corridor_km, zoom)

    sample_points = []
    for i in range(len(valid_pts) - 1):
        p1 = valid_pts[i]
        p2 = valid_pts[i + 1]
        sample_points.append(p1)
        d_lat = p2[0] - p1[0]
        d_lon = p2[1] - p1[1]
        mid_lat = (p1[0] + p2[0]) / 2.0
        seg_dist = math.sqrt((d_lat * 111.0) ** 2 + (d_lon * 111.0 * math.cos(math.radians(mid_lat))) ** 2)
        step_km = max(0.5, min(1.5, corridor_km * 0.5))
        num_steps = max(1, int(math.ceil(seg_dist / step_km)))
        for s in range(1, num_steps):
            frac = s / float(num_steps)
            sample_points.append((p1[0] + d_lat * frac, p1[1] + d_lon * frac))
    sample_points.append(valid_pts[-1])

    unique_tiles = set()
    limit_sq = (corridor_km * 1.15) ** 2
    for s_lat, s_lon in sample_points:
        lat_delta = (corridor_km / 6371.0) * (180.0 / math.pi)
        lon_delta = (corridor_km / (6371.0 * math.cos(math.radians(s_lat)))) * (180.0 / math.pi)
        def l2t(ln, z): return (ln + 180.0) / 360.0 * (2 ** z)
        def a2t(lt, z):
            rad = math.radians(lt)
            return (1.0 - math.log(math.tan(rad) + 1.0 / math.cos(rad)) / math.pi) / 2.0 * (2 ** z)
        min_x = int(l2t(s_lon - lon_delta, zoom))
        max_x = int(l2t(s_lon + lon_delta, zoom))
        min_y = int(a2t(s_lat + lat_delta, zoom))
        max_y = int(a2t(s_lat - lat_delta, zoom))
        for x in range(min(min_x, max_x), max(min_x, max_x) + 1):
            for y in range(min(min_y, max_y), max(min_y, max_y) + 1):
                t_lon = (x + 0.5) / (2 ** zoom) * 360.0 - 180.0
                t_lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * (y + 0.5) / (2 ** zoom)))))
                d_lat_km = (t_lat - s_lat) * 111.0
                d_lon_km = (t_lon - s_lon) * 111.0 * math.cos(math.radians(s_lat))
                if (d_lat_km * d_lat_km + d_lon_km * d_lon_km) <= limit_sq:
                    unique_tiles.add((zoom, x, y))

    return list(unique_tiles)

def sanitize_preset_folder(preset_name):
    if not preset_name or not str(preset_name).strip():
        return "My_Home_Airfield"
    clean = re.sub(r'[^a-zA-Z0-9_\-]+', '_', str(preset_name).strip()).strip('_')
    if clean.lower() in ("default", "my_home_airfield"):
        return "My_Home_Airfield"
    return clean if clean else "My_Home_Airfield"

def run_precache_worker(lat, lon, radius_km, zoom_levels, provider='esri', preset='default', waypoints=None, corridor_km=3.0):
    global precache_state
    precache_state["is_downloading"] = True
    precache_state["status"] = "Calculating tiles..."
    
    preset_folder = sanitize_preset_folder(preset)
    target_cache_dir = os.path.join(tile_cache_dir, preset_folder)
    os.makedirs(target_cache_dir, exist_ok=True)
    
    all_tiles = []
    is_corridor = bool(waypoints and isinstance(waypoints, list) and len(waypoints) > 1)
    if is_corridor:
        tile_set = set()
        for z in zoom_levels:
            tile_set.update(get_tiles_for_waypoints(waypoints, corridor_km, z))
        all_tiles = list(tile_set)
    else:
        for z in zoom_levels:
            all_tiles.extend(get_tiles_for_radius(lat, lon, radius_km, z))

    total = len(all_tiles)
    precache_state["total"] = total
    precache_state["downloaded"] = 0
    precache_state["cached"] = 0
    precache_state["failed"] = 0
    mode_desc = f"corridor ({len(waypoints)} WPs)" if is_corridor else f"{radius_km}km radius"
    precache_state["status"] = f"Downloading {total} tiles [{mode_desc}] for {preset_folder}..."

    # Pre-collect cache search directories strictly matching requested provider family
    search_dirs = [target_cache_dir]
    if os.path.exists(tile_cache_dir):
        try:
            for sub in os.listdir(tile_cache_dir):
                s_path = os.path.join(tile_cache_dir, sub)
                if os.path.isdir(s_path) and s_path not in search_dirs and sub != 'dem':
                    sub_meta = os.path.join(s_path, 'metadata.json')
                    sub_prov = 'esri'
                    if os.path.exists(sub_meta):
                        try:
                            with open(sub_meta, 'r', encoding='utf-8') as smf:
                                sub_prov = json.load(smf).get('provider', 'esri')
                        except Exception:
                            pass
                    if (provider in ('google', 'google_hybrid') and sub_prov in ('google', 'google_hybrid')) or \
                       (provider == 'esri' and sub_prov == 'esri'):
                        search_dirs.append(s_path)
        except Exception:
            pass
    # Only append root tile_cache if provider is ESRI (since root tile_cache contains legacy ESRI tiles)
    if provider == 'esri' and tile_cache_dir not in search_dirs:
        search_dirs.append(tile_cache_dir)

    def proc_tile(tile_info):
        z, x, y = tile_info

        # 1. ALWAYS pre-cache DEM elevation tile for 3D terrain
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

        if provider == 'google':
            tile_filename = f"{z}_{x}_{y}_google.jpg"
            target_names = [f"{z}_{x}_{y}_google.jpg"]
        elif provider == 'google_hybrid':
            tile_filename = f"{z}_{x}_{y}_google_hybrid.jpg"
            target_names = [f"{z}_{x}_{y}_google_hybrid.jpg"]
        else: # esri default
            tile_filename = f"{z}_{x}_{y}_esri.jpg"
            target_names = [f"{z}_{x}_{y}_esri.jpg", f"{z}_{x}_{y}.jpg"]

        tile_path = os.path.join(target_cache_dir, tile_filename)

        # Check if already cached in target preset or matching provider preset (skip 2521-byte placeholders)
        for aname in target_names:
            p1 = os.path.join(target_cache_dir, aname)
            if os.path.exists(p1) and os.path.getsize(p1) > 100 and os.path.getsize(p1) != 2521:
                return 'CACHED'
            for sdir in search_dirs:
                cand_p = os.path.join(sdir, aname)
                if os.path.exists(cand_p) and os.path.getsize(cand_p) > 100 and os.path.getsize(cand_p) != 2521:
                    try:
                        shutil.copy2(cand_p, tile_path)
                        return 'CACHED'
                    except Exception:
                        pass

        data = fetch_tile(z, x, y, provider=provider)
        if data and len(data) > 100 and len(data) != 2521:
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

    meta = {
        "name": str(preset).replace('_', ' '),
        "folder": preset_folder,
        "type": "corridor" if is_corridor else "circular",
        "waypoints_count": len(waypoints) if is_corridor else 0,
        "waypoints": waypoints if is_corridor else [],
        "corridor_km": corridor_km if is_corridor else 0.0,
        "lat": lat,
        "lon": lon,
        "radius_km": radius_km,
        "zooms": zoom_levels,
        "provider": provider,
        "tiles_cached": precache_state["downloaded"] + precache_state["cached"],
        "updated_at": time.time()
    }
    try:
        with open(os.path.join(target_cache_dir, "metadata.json"), "w", encoding="utf-8") as mf:
            json.dump(meta, mf, indent=2)
    except Exception:
        pass

def find_or_synthesize_tile(z, x, y, provider='esri', preset='default', mode='auto', lyrs='s'):
    """
    Finds exact satellite tile on disk or online.
    If offline or pending online download, synthesizes missing zoom level
    from the closest available parent zoom tile using PIL crop & bilinear resize.
    Guarantees zero 404s and seamless LOD display.
    """
    if provider == 'google':
        pref_suffix = '_google.jpg'
        candidate_suffixes = ['_google.jpg']
    elif provider == 'google_hybrid':
        pref_suffix = '_google_hybrid.jpg'
        candidate_suffixes = ['_google_hybrid.jpg']
    else:
        provider = 'esri'
        pref_suffix = '_esri.jpg'
        candidate_suffixes = ['_esri.jpg']

    preset_folder = sanitize_preset_folder(preset)
    preset_dir = os.path.join(tile_cache_dir, preset_folder)
    os.makedirs(preset_dir, exist_ok=True)

    # Search hierarchy: active preset dir first
    search_dirs = [preset_dir]
    if os.path.exists(tile_cache_dir):
        try:
            for sub in os.listdir(tile_cache_dir):
                s_path = os.path.join(tile_cache_dir, sub)
                if os.path.isdir(s_path) and s_path not in search_dirs and sub != 'dem':
                    sub_meta = os.path.join(s_path, 'metadata.json')
                    sub_prov = 'esri'
                    if os.path.exists(sub_meta):
                        try:
                            with open(sub_meta, 'r', encoding='utf-8') as smf:
                                sub_prov = json.load(smf).get('provider', 'esri')
                        except Exception:
                            pass
                    if (provider in ('google', 'google_hybrid') and sub_prov in ('google', 'google_hybrid')) or \
                       (provider == 'esri' and sub_prov == 'esri'):
                        search_dirs.append(s_path)
        except Exception:
            pass
    # Only search root tile_cache if provider is ESRI (since root tile_cache contains legacy ESRI tiles)
    if provider == 'esri' and tile_cache_dir not in search_dirs:
        search_dirs.append(tile_cache_dir)

    # 1. Look for exact tile on disk matching provider
    for sdir in search_dirs:
        for suff in candidate_suffixes:
            cand = os.path.join(sdir, f"{z}_{x}_{y}{suff}")
            if os.path.exists(cand) and os.path.getsize(cand) > 100 and os.path.getsize(cand) != 2521:
                try:
                    with open(cand, 'rb') as f:
                        return f.read(), 'image/jpeg'
                except Exception:
                    pass

    # 1b. If in offline mode, accept cached tile strictly within requested provider family
    if mode == 'offline' or not check_internet_reachability():
        offline_suffixes = candidate_suffixes if provider in ('google', 'google_hybrid') else ['_esri.jpg', '.jpg']
        for sdir in search_dirs:
            for suff in offline_suffixes:
                cand = os.path.join(sdir, f"{z}_{x}_{y}{suff}")
                if os.path.exists(cand) and os.path.getsize(cand) > 100 and os.path.getsize(cand) != 2521:
                    try:
                        with open(cand, 'rb') as f:
                            return f.read(), 'image/jpeg'
                    except Exception:
                        pass

    # 2. If online/auto mode and internet is reachable, fetch tile from remote server
    if mode != 'offline' and check_internet_reachability():
        data = fetch_tile(z, x, y, provider=provider, lyrs=lyrs)
        if data and len(data) > 100 and len(data) != 2521:
            target_path = os.path.join(preset_dir, f"{z}_{x}_{y}{pref_suffix}")
            try:
                with open(target_path, 'wb') as f:
                    f.write(data)
            except Exception:
                pass
            return data, 'image/jpeg'

    # 3. Dynamic LOD Parent Zoom Synthesis (for offline mode or when remote fetch fails)
    # If the user has Zoom 17 cached, and requests Zoom 18, 19, 20 or Zoom 16, 15:
    # Crop the exact quadrant from the nearest ancestor zoom and resize to 256x256 via PIL
    for pz in range(z - 1, max(0, z - 6), -1):
        dz = z - pz
        px = x >> dz
        py = y >> dz

        parent_file = None
        for sdir in search_dirs:
            for suff in (candidate_suffixes if mode != 'offline' else ['_esri.jpg', '_google.jpg', '_google_hybrid.jpg', '.jpg']):
                p_cand = os.path.join(sdir, f"{pz}_{px}_{py}{suff}")
                if os.path.exists(p_cand) and os.path.getsize(p_cand) > 100:
                    parent_file = p_cand
                    break
            if parent_file:
                break

        if not parent_file and mode != 'offline' and check_internet_reachability() and pz >= 12:
            p_data = fetch_tile(pz, px, py, provider=provider, lyrs=lyrs)
            if p_data and len(p_data) > 100 and len(p_data) != 2521:
                p_cand_save = os.path.join(preset_dir, f"{pz}_{px}_{py}{pref_suffix}")
                try:
                    with open(p_cand_save, 'wb') as f:
                        f.write(p_data)
                    parent_file = p_cand_save
                except Exception:
                    pass

        if parent_file:
            try:
                p_img = Image.open(parent_file)
                sub_span = 1 << dz
                sub_mask = sub_span - 1
                sub_x = x & sub_mask
                sub_y = y & sub_mask

                w, h = p_img.size
                crop_w = w / sub_span
                crop_h = h / sub_span

                x0 = int(round(sub_x * crop_w))
                y0 = int(round(sub_y * crop_h))
                x1 = int(round(x0 + crop_w))
                y1 = int(round(y0 + crop_h))

                cropped = p_img.crop((x0, y0, x1, y1))
                resized = cropped.resize((256, 256), Image.Resampling.BILINEAR)

                out_io = io.BytesIO()
                resized.save(out_io, format='JPEG', quality=85)
                synth_bytes = out_io.getvalue()

                # Cache synthesized tile for instant future reads
                if mode == 'offline':
                    try:
                        save_p = os.path.join(preset_dir, f"{z}_{x}_{y}{pref_suffix}")
                        with open(save_p, 'wb') as sf:
                            sf.write(synth_bytes)
                    except Exception:
                        pass
                return synth_bytes, 'image/jpeg'
            except Exception:
                pass

    # 4. If zoomed out (e.g. asking for Zoom 15 when Zoom 17 is cached), downsample child
    for cz in range(z + 1, min(21, z + 3)):
        dz = cz - z
        cx = x << dz
        cy = y << dz
        child_file = None
        for sdir in search_dirs:
            for suff in (candidate_suffixes if mode != 'offline' else ['_esri.jpg', '_google.jpg', '_google_hybrid.jpg', '.jpg']):
                c_cand = os.path.join(sdir, f"{cz}_{cx}_{cy}{suff}")
                if os.path.exists(c_cand) and os.path.getsize(c_cand) > 100:
                    child_file = c_cand
                    break
            if child_file:
                break
        if child_file:
            try:
                c_img = Image.open(child_file)
                resized = c_img.resize((256, 256), Image.Resampling.BILINEAR)
                out_io = io.BytesIO()
                resized.save(out_io, format='JPEG', quality=80)
                return out_io.getvalue(), 'image/jpeg'
            except Exception:
                pass

    return None

def find_or_synthesize_dem(z, x, y, mode='auto'):
    """
    Finds or synthesizes Terrarium DEM tile for 3D elevation.
    If missing, checks parent DEM tile. If none exists, generates
    a synthetic 0m flat sea-level tile RGB(128, 0, 0) so 3D terrain NEVER 404s!
    """
    dem_z = min(z, 15)
    zoom_diff = z - dem_z
    dem_x = x >> zoom_diff
    dem_y = y >> zoom_diff

    dem_filename = f"{dem_z}_{dem_x}_{dem_y}.png"
    dem_file = os.path.join(dem_cache_dir, dem_filename)

    # 1. Exact cached DEM tile
    if os.path.exists(dem_file) and os.path.getsize(dem_file) > 100:
        try:
            with open(dem_file, 'rb') as f:
                return f.read(), 'image/png'
        except Exception:
            pass

    # 2. Remote DEM fetch if online and reachable
    if mode != 'offline' and check_internet_reachability():
        data = fetch_dem_tile(dem_z, dem_x, dem_y)
        if data and len(data) > 100:
            try:
                with open(dem_file, 'wb') as df:
                    df.write(data)
            except Exception:
                pass
            return data, 'image/png'

    # 3. Dynamic LOD Parent DEM Synthesis
    for pz in range(dem_z - 1, max(0, dem_z - 4), -1):
        dz = dem_z - pz
        px = dem_x >> dz
        py = dem_y >> dz
        p_cand = os.path.join(dem_cache_dir, f"{pz}_{px}_{py}.png")
        if os.path.exists(p_cand) and os.path.getsize(p_cand) > 100:
            try:
                p_img = Image.open(p_cand)
                sub_span = 1 << dz
                sub_mask = sub_span - 1
                sub_x = dem_x & sub_mask
                sub_y = dem_y & sub_mask

                w, h = p_img.size
                crop_w = w / sub_span
                crop_h = h / sub_span

                x0 = int(round(sub_x * crop_w))
                y0 = int(round(sub_y * crop_h))
                x1 = int(round(x0 + crop_w))
                y1 = int(round(y0 + crop_h))

                cropped = p_img.crop((x0, y0, x1, y1))
                resized = cropped.resize((256, 256), Image.Resampling.NEAREST)
                out_io = io.BytesIO()
                resized.save(out_io, format='PNG')
                synth_bytes = out_io.getvalue()
                try:
                    with open(dem_file, 'wb') as df:
                        df.write(synth_bytes)
                except Exception:
                    pass
                return synth_bytes, 'image/png'
            except Exception:
                pass

    # 4. Universal flat 0m sea-level Terrarium tile fallback (RGB 128, 0, 0 -> 0.0m MSL)
    # Guarantees DEM requests never 404 in memory, but NEVER writes flat synthetic fallback to disk
    # so disk cache is never poisoned and real elevation can load on subsequent requests.
    try:
        flat_dem = Image.new('RGB', (256, 256), color=(128, 0, 0))
        out_io = io.BytesIO()
        flat_dem.save(out_io, format='PNG')
        flat_bytes = out_io.getvalue()
        return flat_bytes, 'image/png'
    except Exception:
        return b'', 'image/png'

class RobustThreadingHTTPServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        exc_type, exc_val, _ = sys.exc_info()
        # Suppress normal client aborts / resets (e.g. WinError 10053 / 10054 on cancelled tile requests)
        if exc_type in (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            return
        super().handle_error(request, client_address)

def start_http_server():
    vis_dir = os.path.join(os.path.dirname(__file__), '..', 'visualizer')
    os.chdir(vis_dir)
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def end_headers(self):
            try:
                if not getattr(self, '_is_tile', False):
                    self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
                    self.send_header('Pragma', 'no-cache')
                    self.send_header('Expires', '0')
                self.send_header('Access-Control-Allow-Origin', '*')
                super().end_headers()
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
                pass

        def send_error(self, code, message=None, explain=None):
            try:
                super().send_error(code, message=message, explain=explain)
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
                pass

        def finish(self):
            try:
                super().finish()
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
                pass

        def handle_one_request(self):
            try:
                super().handle_one_request()
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
                pass

        def do_GET(self):
            # 1. Tile proxy and disk caching: /tiles/<z>/<x>/<y>.jpg
            if self.path.startswith('/tiles/'):
                self._is_tile = True
                try:
                    clean_path = self.path.split('?')[0]
                    query_str = self.path.split('?')[1] if '?' in self.path else ''
                    query_params = urllib.parse.parse_qs(query_str)
                    mode = query_params.get('mode', ['auto'])[0]
                    provider = query_params.get('provider', ['esri'])[0].lower()
                    preset = query_params.get('preset', ['default'])[0]
                    lyrs = query_params.get('lyrs', ['s'])[0]
                    parts = clean_path.split('/')
                    if len(parts) >= 5:
                        z = int(parts[2])
                        x = int(parts[3])
                        y = int(parts[4].split('.')[0])

                        res = find_or_synthesize_tile(z, x, y, provider=provider, preset=preset, mode=mode, lyrs=lyrs)
                        if res:
                            data, content_type = res
                            try:
                                self.send_response(200)
                                self.send_header('Content-Type', content_type)
                                self.send_header('Content-Length', str(len(data)))
                                self.send_header('Cache-Control', 'public, max-age=31536000')
                                self.end_headers()
                                self.wfile.write(data)
                            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
                                pass
                            return
                except Exception:
                    pass
                try:
                    self.send_error(404, "Tile not found")
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
                    pass
                return

            # 1b. DEM Elevation Tile proxy and disk caching: /dem/<z>/<x>/<y>.png
            elif self.path.startswith('/dem/'):
                self._is_tile = True
                try:
                    clean_path = self.path.split('?')[0]
                    query_str = self.path.split('?')[1] if '?' in self.path else ''
                    query_params = urllib.parse.parse_qs(query_str)
                    mode = query_params.get('mode', ['auto'])[0]
                    parts = clean_path.split('/')
                    if len(parts) >= 5:
                        z = int(parts[2])
                        x = int(parts[3])
                        y = int(parts[4].split('.')[0])

                        res = find_or_synthesize_dem(z, x, y, mode=mode)
                        if res:
                            data, content_type = res
                            try:
                                self.send_response(200)
                                self.send_header('Content-Type', content_type)
                                self.send_header('Content-Length', str(len(data)))
                                self.send_header('Cache-Control', 'public, max-age=31536000')
                                self.end_headers()
                                self.wfile.write(data)
                            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
                                pass
                            return
                except Exception:
                    pass
                try:
                    self.send_error(404, "DEM Tile not found")
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
                    pass
                return

            # 2. Clear cache endpoint: /api/clear_cache?preset=...
            elif self.path.startswith('/api/clear_cache'):
                try:
                    query_str = self.path.split('?')[1] if '?' in self.path else ''
                    query_params = urllib.parse.parse_qs(query_str)
                    preset = query_params.get('preset', [''])[0]
                    cleared_count = 0

                    if not preset:
                        self.send_error(400, "Missing preset parameter")
                        return

                    if preset != 'all':
                        preset_folder = sanitize_preset_folder(preset)
                        target_dir = os.path.join(tile_cache_dir, preset_folder)
                        if os.path.exists(target_dir):
                            for f in os.listdir(target_dir):
                                if f.endswith('.jpg') or f.endswith('.png'):
                                    try:
                                        os.remove(os.path.join(target_dir, f))
                                        cleared_count += 1
                                    except Exception: pass
                            # Synchronize metadata.json to reflect 0 cached tiles
                            meta_file = os.path.join(target_dir, 'metadata.json')
                            if os.path.exists(meta_file):
                                try:
                                    with open(meta_file, 'r', encoding='utf-8') as mf:
                                        mdata = json.load(mf)
                                    mdata['tiles_cached'] = 0
                                    mdata['updated_at'] = time.time()
                                    with open(meta_file, 'w', encoding='utf-8') as mf:
                                        json.dump(mdata, mf, indent=2)
                                except Exception:
                                    pass
                    else:
                        for root, dirs, files in os.walk(tile_cache_dir):
                            for f in files:
                                if f.endswith('.jpg') or f.endswith('.png'):
                                    try:
                                        os.remove(os.path.join(root, f))
                                        cleared_count += 1
                                    except Exception: pass
                                elif f == 'metadata.json':
                                    try:
                                        mf_path = os.path.join(root, f)
                                        with open(mf_path, 'r', encoding='utf-8') as mf:
                                            mdata = json.load(mf)
                                        mdata['tiles_cached'] = 0
                                        with open(mf_path, 'w', encoding='utf-8') as mf:
                                            json.dump(mdata, mf, indent=2)
                                    except Exception:
                                        pass

                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "cleared", "count": cleared_count}).encode('utf-8'))
                    return
                except Exception as e:
                    self.send_error(500, str(e))
                    return

            # 2b. Waypoints API: /api/waypoints
            elif self.path.startswith('/api/waypoints'):
                try:
                    wps = [w for w in mission_handler.waypoints if w is not None] if mission_handler.waypoints else []
                    if not wps and os.path.exists(mission_handler.cache_file):
                        try:
                            with open(mission_handler.cache_file, 'r', encoding='utf-8') as cf:
                                wps = json.load(cf)
                        except Exception:
                            pass
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"waypoints": wps, "count": len(wps)}).encode('utf-8'))
                    return
                except Exception as e:
                    self.send_error(500, str(e))
                    return

            # 2c. Serial Ports List API: /api/list_ports
            elif self.path.startswith('/api/list_ports'):
                ports_list = []
                try:
                    import serial.tools.list_ports
                    for p in serial.tools.list_ports.comports():
                        ports_list.append({
                            "device": p.device,
                            "description": p.description or p.device,
                            "manufacturer": p.manufacturer or ""
                        })
                except Exception:
                    pass
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"ports": ports_list}).encode('utf-8'))
                return

            # 2d. MAVLink Status API: /api/mavlink_status
            elif self.path.startswith('/api/mavlink_status'):
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({
                    "connected": heartbeat_received,
                    "url": MAVLINK_URL,
                    "target": MAVLINK_DEVICE,
                    "baud": MAVLINK_BAUD
                }).encode('utf-8'))
                return

            # 3. Cache status API: /api/cache_status?preset=...
            elif self.path.startswith('/api/cache_status'):
                try:
                    query_str = self.path.split('?')[1] if '?' in self.path else ''
                    query_params = urllib.parse.parse_qs(query_str)
                    preset = query_params.get('preset', ['default'])[0]
                    preset_folder = sanitize_preset_folder(preset)
                    target_dir = os.path.join(tile_cache_dir, preset_folder)

                    preset_files = [f for f in os.listdir(target_dir) if f.endswith('.jpg') or f.endswith('.png')] if os.path.exists(target_dir) else []
                    preset_mb = sum(os.path.getsize(os.path.join(target_dir, f)) for f in preset_files) / (1024 * 1024) if preset_files else 0.0

                    total_files_count = 0
                    total_bytes = 0
                    for root, dirs, files in os.walk(tile_cache_dir):
                        for f in files:
                            if f.endswith('.jpg') or f.endswith('.png'):
                                total_files_count += 1
                                try:
                                    total_bytes += os.path.getsize(os.path.join(root, f))
                                except Exception: pass

                    total_mb = total_bytes / (1024 * 1024)

                    available_folders = []
                    preset_metadata_map = {}
                    if os.path.exists(tile_cache_dir):
                        for item in os.listdir(tile_cache_dir):
                            item_path = os.path.join(tile_cache_dir, item)
                            if os.path.isdir(item_path) and item != 'dem':
                                available_folders.append(item)
                                meta_file = os.path.join(item_path, 'metadata.json')
                                if os.path.exists(meta_file):
                                    try:
                                        with open(meta_file, 'r', encoding='utf-8') as mf:
                                            mdata = json.load(mf)
                                        # Count actual disk files to ensure metadata is dynamically truthful
                                        actual_t = len([f for f in os.listdir(item_path) if f.endswith('.jpg') or f.endswith('.png')])
                                        mdata['tiles_cached'] = actual_t
                                        # Backfill waypoints from waypoints_cache.json if missing in corridor preset
                                        is_corridor_folder = (mdata.get('type') == 'corridor') or ('corridor' in item.lower())
                                        if is_corridor_folder and (not mdata.get('waypoints') or len(mdata.get('waypoints', [])) <= 1):
                                            if os.path.exists(mission_handler.cache_file):
                                                try:
                                                    with open(mission_handler.cache_file, 'r', encoding='utf-8') as cf:
                                                        disk_wps = json.load(cf)
                                                    if isinstance(disk_wps, list) and len(disk_wps) > 1:
                                                        mdata['waypoints'] = disk_wps
                                                        mdata['type'] = 'corridor'
                                                        with open(meta_file, 'w', encoding='utf-8') as mf:
                                                            json.dump(mdata, mf, indent=2)
                                                except Exception: pass
                                        preset_metadata_map[item] = mdata
                                    except Exception:
                                        pass
                                elif item == 'My_Home_Airfield':
                                    preset_metadata_map[item] = {
                                        "name": "My Home Airfield",
                                        "folder": "My_Home_Airfield",
                                        "lat": 8.3105,
                                        "lon": 77.3137,
                                        "radius_km": 3.0,
                                        "zooms": [17, 16, 15],
                                        "provider": "esri",
                                        "tiles_cached": len([f for f in os.listdir(item_path) if f.endswith('.jpg')])
                                    }
                                else:
                                    # Fallback: estimate coordinates from first cached tile
                                    try:
                                        tfiles = [f for f in os.listdir(item_path) if f.endswith('.jpg')]
                                        if tfiles:
                                            parts = tfiles[0].split('_')
                                            if len(parts) >= 3 and parts[0].isdigit() and parts[1].isdigit():
                                                tz, tx = int(parts[0]), int(parts[1])
                                                ty = int(parts[2].split('.')[0])
                                                n = 2.0 ** tz
                                                t_lon = tx / n * 360.0 - 180.0
                                                lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ty / n)))
                                                t_lat = math.degrees(lat_rad)
                                                preset_metadata_map[item] = {
                                                    "name": item.replace('_', ' '),
                                                    "folder": item,
                                                    "lat": round(t_lat, 5),
                                                    "lon": round(t_lon, 5),
                                                    "radius_km": 3.0,
                                                    "zooms": [tz],
                                                    "provider": "esri",
                                                    "tiles_cached": len(tfiles)
                                                }
                                    except Exception:
                                        pass

                    resp = {
                        "preset_folder": preset_folder,
                        "preset_dir": f"tile_cache/{preset_folder}/",
                        "cached_count": len(preset_files),
                        "cached_mb": round(preset_mb, 2),
                        "total_cached_count": total_files_count,
                        "total_cached_mb": round(total_mb, 2),
                        "is_online": check_internet_reachability(),
                        "available_presets": available_folders,
                        "preset_metadata": preset_metadata_map,
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
                    corridor_km = float(data.get('corridor_km', 3.0))
                    waypoints = data.get('waypoints')
                    zooms = data.get('zooms', [17])
                    provider = data.get('provider', 'esri')
                    preset = data.get('preset', 'default')
                    if not precache_state["is_downloading"]:
                        threading.Thread(
                            target=run_precache_worker,
                            args=(lat, lon, radius, zooms, provider, preset, waypoints, corridor_km),
                            daemon=True
                        ).start()
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

            elif self.path.startswith('/api/connect_mavlink'):
                content_len = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_len).decode('utf-8') if content_len > 0 else '{}'
                try:
                    pdata = json.loads(body) if body else {}
                    raw_target = pdata.get("target", "udpin:0.0.0.0:14550")
                    req_baud = int(pdata.get("baud", 115200))
                    success, res_msg = switch_mavlink_target(raw_target, req_baud)
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "success": success,
                        "message": res_msg,
                        "url": MAVLINK_URL,
                        "target": MAVLINK_DEVICE
                    }).encode('utf-8'))
                except Exception as e:
                    self.send_response(500)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
                return

            return super().do_POST()

        def log_message(self, format, *args): pass
    
    try:
        # Use ThreadingHTTPServer so a single browser's Keep-Alive doesn't block other connections
        with RobustThreadingHTTPServer(("0.0.0.0", 8000), QuietHandler) as httpd:
            http_server_ready_event.set()
            print("HTTP Web Server with Offline Tile Cache started on port 8000")
            httpd.serve_forever()
    except OSError as e:
        http_server_ready_event.set()
        if getattr(e, 'errno', None) in (10048, 98):
            print("[Notice] HTTP Port 8000 is already in use by an active server.")
        else:
            raise

async def main():
    # Start the HTTP server in the background
    threading.Thread(target=start_http_server, daemon=True).start()

    try:
        server = await websockets.serve(ws_handler, "0.0.0.0", 8766)
        ws_server_ready_event.set()
        print("WebSocket Server started on port 8766")
        await asyncio.gather(server.wait_closed(), mavlink_listener())
    except OSError as e:
        ws_server_ready_event.set()
        if getattr(e, 'errno', None) in (10048, 98):
            print("\n" + "="*65)
            print(" [!] ERROR: Port 8766 is already in use by another Python instance.")
            print(" An existing server.py process is already running.")
            print(" To free the port, run in PowerShell:")
            print("   Get-Process python | Stop-Process -Force")
            print("="*65 + "\n")
        raise

def start_asyncio_loop():
    # Set up a resilient event loop that automatically recovers if connection is interrupted
    while True:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(main())
        except Exception as e:
            print(f"[AsyncIO Loop] Recovering from connection event: {e}")
            time.sleep(1)

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
    parser.add_argument("--connect", "--mavlink", "-c", default=None, help="MAVLink target (e.g. tcp:127.0.0.1:5762, udpin:0.0.0.0:14550, COM3:115200)")
    parser.add_argument("--udp", "-u", default=None, help="Connect via UDP port or IP:PORT (e.g. 14550, 0.0.0.0:14550)")
    parser.add_argument("--com", default=None, help="Connect via serial COM port (e.g. COM3 or COM3:115200)")
    parser.add_argument("--baud", "-b", type=int, default=115200, help="Serial baud rate (default: 115200)")
    parser.add_argument("target", nargs="?", default=None, help="Optional positional MAVLink target (e.g. 14550, udpin:0.0.0.0:14550, COM3)")
    args, unknown = parser.parse_known_args()

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
        def _deferred_open_browser():
            http_server_ready_event.wait(timeout=3.0)
            print("[Visualizer] Opening browser tab at: http://127.0.0.1:8000/sharkee_hud.html\n")
            open_browser("http://127.0.0.1:8000/sharkee_hud.html")
        threading.Thread(target=_deferred_open_browser, daemon=True).start()
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
        
        # Await HTTP Web Server (Port 8000) & WebSocket Telemetry Gateway (Port 8766) readiness
        http_server_ready_event.wait(timeout=3.0)
        ws_server_ready_event.wait(timeout=3.0)

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



