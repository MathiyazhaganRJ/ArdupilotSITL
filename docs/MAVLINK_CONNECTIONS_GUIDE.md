# Sharkee Avionics HUD: MAVLink Telemetry Connection & Interface Manual

**Document Identifier**: `DOC-AVN-CON-001`  
**Revision**: `1.0`  
**Classification**: Technical Reference & Operational Guide  
**System Targets**: ArduPilot (ArduPlane, QuadPlane VTOL, ArduCopter, Rover), PX4 Autopilot, ArduPilot SITL Simulator  

---

## 1. System Architecture Overview

The Sharkee Avionics Visualizer and Telemetry Server operates as a high-throughput, low-latency telemetry processing node. It bridges heterogeneous MAVLink physical and network communication layers with real-time browser-based 3D HUD instrumentation via WebSockets.

```
+-------------------------------------------------------------------------+
|                        Telemetry Source Layer                           |
|                                                                         |
|  +------------------+   +-------------------+   +--------------------+  |
|  | Physical Vehicle |   |   ArduPilot SITL  |   | GCS Proxy / Mirror |  |
|  | Flight Controller|   | Software-in-Loop  |   | (MAVProxy / MP/QGC)|  |
|  +--------+---------+   +---------+---------+   +---------+----------+  |
|           |                       |                       |             |
|    UART / USB (COMx)         TCP (5760-5763)       UDP (14550/14558)    |
+-----------+-----------------------+-----------------------+-------------+
            |                       |                       |
            +-------------------+   |   +-------------------+
                                |   |   |
                                v   v   v
+-------------------------------------------------------------------------+
|                  Sharkee Telemetry Backend (server.py)                  |
|                                                                         |
|  - Address Normalizer & Link Router (CLI / Environmental)               |
|  - Multi-Modal Hardware Resolution (board_types.py)                     |
|  - MAVLink Dialect Decoder (ardupilotmega v1.0 / v2.0)                  |
|  - Mission Handler & Dynamic Stream Rate Governor                       |
|  - Secondary Node Addressing (SysID: 254, CompID: 190)                  |
+-----------------------------------+-------------------------------------+
                                    |
                    WebSocket Streaming (Port 8766)
                    HTTP Static Tile Server (Port 8000)
                                    v
+-------------------------------------------------------------------------+
|                  Sharkee 3D Avionics HUD (Visualizer)                   |
|                                                                         |
|  - Primary Flight Display (PFD) / Synthetic Vision System (SVS)         |
|  - Engine Indication and Crew Alerting System (EICAS / Motors)          |
|  - 3D Terrain Elevation Engine & Mission Navigation Track               |
|  - Dynamic Live MAVLink Port Reconnection Dialog                        |
+-------------------------------------------------------------------------+
```

---

## 2. Command-Line Interface (CLI) Specification

The server is initiated via terminal using `python server/server.py` (or `python server.py` from within the `server/` directory). It accepts explicit connection switches, network addresses, or serial device identifiers.

### Command-Line Arguments

| Flag | Long Alternative | Format / Value | Description |
| :--- | :--- | :--- | :--- |
| `-u` | `--udp` | `[HOST:]PORT` | Binds a UDP listener on the specified local address and port (e.g. `14550`, `127.0.0.1:14558`, `0.0.0.0:14550`). |
| | `--com` | `COMx` | Opens an exclusive serial connection to the designated physical COM port on Windows (e.g. `COM6`, `COM3`). |
| `-b` | `--baud` | `INTEGER` | Specifies baud rate for serial communication (defaults to `115200`). |
| `-c` | `--connect`, `--mavlink` | `URI_STRING` | Explicit universal MAVLink connection target (`udpin:`, `udpout:`, `tcp:`, `tcpin:`, `COMx`). |

---

## 3. Telemetry Connection Topologies

### Mode 1: Physical Flight Controller via Direct USB Serial

Use this mode when connecting the flight controller directly to the ground station workstation via USB without running third-party ground station software simultaneously.

```
[Flight Controller] <=== Direct USB Cable ===> [Workstation: COM6] ===> [server.py]
```

#### Terminal Invocation
```powershell
# Default baud rate (115200 baud)
python server/server.py --com COM6

# High-speed telemetry link (e.g. 921600 or 57600 baud)
python server/server.py --com COM6 --baud 921600
```

#### Operational Characteristics
* **Exclusive Port Access**: Windows permits only one application to hold an open handle on a serial port at any given time. Ensure Mission Planner or MAVProxy is disconnected before launching in this mode.
* **Automatic Port Lock Fallback**: If `COMx` is locked by another process, `server.py` emits a warning and gracefully falls back to UDP listener mode (`udpin:0.0.0.0:14550`), keeping the HUD online.
* **Hardware Detection**: Directly queries `AUTOPILOT_VERSION` (Message 148) and `MAV_CMD_DO_SEND_BANNER` (Command 42428), correlating Windows USB descriptors and STM32 Unique IDs immediately.

---

### Mode 2: MAVProxy Telemetry Mirror (Recommended Multi-Client Architecture)

Use this mode when MAVProxy owns the primary serial connection to the flight controller and forwards a secondary telemetry stream to the visualizer over UDP.

```
[Flight Controller] <--- Serial (COM6) ---> [MAVProxy]
                                                |
                                        UDP Forwarding (14558)
                                                v
                                           [server.py]
```

#### Step 1: Launch MAVProxy
Open a terminal and connect MAVProxy to the flight controller:
```powershell
mavproxy.exe --master com6 --baud 115200
```

#### Step 2: Add UDP Telemetry Output
In the MAVProxy interactive console, add an output directed to local port 14558:
```text
MAV> output add 127.0.0.1:14558
```
*(Alternatively, launch MAVProxy with the output pre-configured)*:
```powershell
mavproxy.exe --master com6 --baud 115200 --out 127.0.0.1:14558
```

#### Step 3: Launch Sharkee Telemetry Server
Open a second terminal window and run:
```powershell
python server/server.py --udp 127.0.0.1:14558
```

#### Operational Characteristics
* **SysID Loopback Immunity**: The visualizer connects using `source_system=254, source_component=190`. MAVProxy preserves and routes packets from SysID 254 without dropping them as self-echo reflections.
* **Non-Blocking Zero-Reboot Hardware Identification**: The visualizer reads the startup boot record from the active `mav.tlog` generated by MAVProxy, matching the 96-bit STM32 UID against Windows USB device `COM6` to instantly display the exact hardware name (e.g., `SpeedyBee F405-WING`).

---

### Mode 3: Mission Planner Telemetry Mirror

Use this mode when Mission Planner is connected to the vehicle over USB or telemetry radio, and you wish to feed live flight data into the Sharkee HUD concurrently.

```
[Flight Controller] <--- Serial / Telemetry ---> [Mission Planner]
                                                       |
                                               MAVLink Mirror (UDP)
                                                       v
                                                  [server.py]
```

#### Step 1: Configure MAVLink Mirror in Mission Planner
1. Connect Mission Planner to the vehicle as normal on `COM6`.
2. Press **Ctrl + F** to open the Mission Planner *Temp Tools / Options* window.
3. Click the **Mavlink** button (or **Telemetry Mirror**).
4. Select **UDP Client** (or **UDP Host**) and specify:
   * **Host IP**: `127.0.0.1`
   * **Remote Port**: `14550` (or `14558`)
5. Click **Connect** / **Write**.

#### Step 2: Launch Sharkee Telemetry Server
```powershell
# Default auto-discovery automatically binds to 14550:
python server/server.py

# Or explicitly designate the port:
python server/server.py --udp 14550
```

---

### Mode 4: QGroundControl (QGC) Telemetry Forwarding

Use this mode when operating with QGroundControl on the same or an adjacent computer.

#### Step 1: Enable MAVLink Forwarding in QGC
1. In QGroundControl, navigate to **Application Settings** (Top-Left Q icon -> *Application Settings*).
2. Select the **Comm Links** or **Mavlink** tab.
3. Enable **Enable MAVLink Forwarding**.
4. Set the host IP to `127.0.0.1` and the target UDP port to `14550`.

#### Step 2: Launch Sharkee Telemetry Server
```powershell
python server/server.py --udp 14550
```

---

### Mode 5: ArduPilot Software-in-the-Loop (SITL) Simulation

Use this mode for software development, flight testing, synthetic mission rehearsal, and aerodynamics analysis with JSBSim or ArduPilot SITL.

```
[sim_vehicle.py (ArduPlane SITL)] <=== TCP 127.0.0.1:5762 ===> [server.py]
```

#### Step 1: Launch ArduPilot SITL
In WSL, Linux, or Cygwin/Windows terminal:
```bash
# Launch QuadPlane VTOL SITL instance
sim_vehicle.py -v ArduPlane -f quadplane --console --map
```
ArduPilot SITL opens listening TCP sockets on:
* `5760`: Console / Primary GCS
* `5762`: Secondary GCS link #1
* `5763`: Secondary GCS link #2

#### Step 2: Launch Sharkee Telemetry Server
```powershell
# Explicit connection to SITL secondary port:
python server/server.py --connect tcp:127.0.0.1:5762

# Autonomous discovery:
# If launched with no arguments, server.py scans 5762, 5763, and 5760 automatically.
python server/server.py
```

#### Operational Characteristics
* **SITL Autopilot Tagging**: The backend flags `is_network_sitl = True`, assigning `FC Hardware: SITL` in Aviation Cyan (`#00e5ff`) on the HUD visualizer.
* **Full Bidirectional Capability**: Waypoint fetch, mission sync, flight mode switching, and parameter inspection operate with zero physical bus constraints.

---

### Mode 6: Remote Wireless Telemetry & Onboard Companion Computers

Use this mode when communicating with an aircraft in flight over long-range RF links, ESP32 WiFi bridges, or cellular companion computer tunnels.

#### Topology A: SiK Telemetry Radio (433 MHz / 915 MHz USB Dongle)
Plug the ground radio transceiver USB dongle into the workstation:
```powershell
python server/server.py --com COM12 --baud 57600
```

#### Topology B: Onboard Companion Computer (Raspberry Pi / Jetson / Zero 2W)
An onboard computer running MAVROS, MAVProxy, or Rpanion forwards telemetry over WiFi or LTE:
* **Aircraft side**: MAVProxy streams to ground station IP: `output add 192.168.1.100:14550`
* **Ground station side**:
  ```powershell
  python server/server.py --udp 0.0.0.0:14550
  ```

---

## 4. Summary Quick-Reference Matrix

| Telemetry Source | Workstation Link | Protocol String | Terminal Launch Command |
| :--- | :--- | :--- | :--- |
| **Physical FC Direct** | Direct USB Cable | `COMx` | `python server/server.py --com COM6` |
| **Physical FC Direct (High Speed)** | Direct USB Cable | `COMx:Baud` | `python server/server.py --com COM6 --baud 921600` |
| **MAVProxy Output** | Local UDP Bridge | `udpin:127.0.0.1:14558` | `python server/server.py --udp 127.0.0.1:14558` |
| **Mission Planner Mirror** | Local UDP Broadcast | `udpin:0.0.0.0:14550` | `python server/server.py --udp 14550` |
| **QGroundControl Mirror** | Local UDP Broadcast | `udpin:0.0.0.0:14550` | `python server/server.py --udp 14550` |
| **ArduPilot SITL Simulator** | Local TCP Stream | `tcp:127.0.0.1:5762` | `python server/server.py --connect tcp:127.0.0.1:5762` |
| **Autonomous Discovery** | Auto-Scan TCP / UDP | *Automatic* | `python server/server.py` |
| **Remote Aircraft (WiFi/LTE)** | Network UDP Broadcast | `udpin:0.0.0.0:14550` | `python server/server.py --udp 0.0.0.0:14550` |
| **SiK Telemetry Radio** | USB Radio Transceiver | `COMx:57600` | `python server/server.py --com COM12 --baud 57600` |

---

## 5. Live Runtime Port Switching (In-HUD Dialog)

The Sharkee visualizer permits changing connection targets on the fly without terminating the Python server process or closing browser sessions.

1. Open the visualizer in your web browser: `http://localhost:8000`
2. Expand the left-hand **Telemetry Drawer** (`[<]` tab).
3. Locate the **MAVLink Port** row (under *Link Status*).
4. Click the blue port address string (e.g., `udpin:0.0.0.0:14550` or the edit pencil icon).
5. Enter any valid connection target in the interactive prompt:
   * Direct Serial: `COM6` or `COM6:115200`
   * UDP Receiver: `14558` or `127.0.0.1:14558` or `udpin:0.0.0.0:14550`
   * TCP Simulator: `tcp:127.0.0.1:5762`
6. Press **OK**. The backend cleanly closes its previous socket/serial handle and connects to the new target within 500 milliseconds.

---

## 6. Diagnostics & Troubleshooting Guide

### Issue 1: `PermissionError: [Errno 13] Access is denied: 'COMx'`
* **Cause**: Another process (typically Mission Planner, MAVProxy, or Arduino Serial Monitor) has locked the serial handle on that COM port.
* **Resolution**:
  1. Either close Mission Planner / MAVProxy, **OR**
  2. Route telemetry through MAVProxy/Mission Planner using a UDP mirror (`--udp 14558` or `--udp 14550`).
  3. The server automatically falls back to UDP listener mode on `14550` when access is denied.

### Issue 2: FC Hardware Status Stuck on `Detecting FC...`
* **Cause**: Intermediary bridge filtered the one-time boot banner, or SysID collision occurred.
* **Resolution**:
  1. Ensure you are running the latest backend with multi-modal environmental resolution (`board_types.py`).
  2. Ensure your GCS bridge outputs MAVLink2 packets.
  3. If operating over a remote wireless network link, trigger a vehicle banner request or power cycle the vehicle once.

### Issue 3: Telemetry Connects but Flight Mode or Heartbeat is Stagnant
* **Cause**: Target MAVLink stream rates are throttled on the vehicle.
* **Resolution**:
  The backend automatically requests the following stream rates upon initial heartbeat receipt:
  * `EXTRA1` (Attitude & Roll/Pitch/Yaw rates): `30 Hz`
  * `POSITION` (Global position and velocities): `30 Hz`
  * `EXTRA2` (VFR_HUD airspeed and throttle): `10 Hz`
  * `RC_CHANNELS` (Motor and servo positions): `10 Hz`
  * `EXTENDED_STATUS` (Sensors and GPS status): `5 Hz`
  * `TERRAIN_REPORT` (Msg 136): `2 Hz`
  * `WIND` (Msg 168): `10 Hz`

### Issue 4: Dual UDP Socket Collision on Windows
* **Cause**: On Windows, running two sockets on the same port where one binds to `0.0.0.0` and the other binds to `127.0.0.1` causes Windows to loop back local packets to the `127.0.0.1` socket.
* **Resolution**:
  * Set MAVProxy to output to `127.0.0.1:14558`.
  * Set `server.py` to listen on `--udp 127.0.0.1:14558`.
  * Using `source_system=254` avoids any dropped packets.
