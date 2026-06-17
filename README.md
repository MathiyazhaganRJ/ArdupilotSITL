# ArduPilot SITL 3D Web Visualizer

A simple 3D flight visualizer for ArduPilot SITL.

## How to Run

**1. Install Dependencies:**
```bash
pip install pymavlink websockets
```

**2. Start ArduPilot SITL:**
Start your simulation (forward MAVLink telemetry to UDP `127.0.0.1:14555`).
Example Quadplane start command:
```bash
Tools/autotest/sim_vehicle.py -v ArduPlane -f quadplane --console --map
```

**3. Start the Python Server:**
Open a terminal in this directory and run:
```bash
python server.py
```

**4. Open the Visualizer:**
Simply double-click `index.html` to view the 3D simulation in your web browser.

---

## ArduPilot SITL Commands

Run these commands from inside your `~/ardupilot` directory in WSL.

**Standard Fixed Wing (Pusher):**
```bash
Tools/autotest/sim_vehicle.py -v ArduPlane --console --map
```

**QuadPlane (VTOL):**
```bash
Tools/autotest/sim_vehicle.py -v ArduPlane -f quadplane --console --map
```

**Quadcopter:**
```bash
Tools/autotest/sim_vehicle.py -v ArduCopter --console --map
```

**Wipe Parameters (Factory Reset):**
*(Use this if the plane is acting crazy or you are switching from Copters to Planes)*
```bash
Tools/autotest/sim_vehicle.py -v ArduPlane -f quadplane -w --console --map
```

**Spawn at a Specific Airport/Location (`-L` flag):**
*(e.g., KSFO for San Francisco Airport, or CMAC for the test field)*
```bash
Tools/autotest/sim_vehicle.py -v ArduPlane -L KSFO --console --map
```

**Spawn at Custom GPS Coordinates:**
*(Format MUST be exactly 4 values: Latitude, Longitude, Altitude, Heading)*
```bash
Tools/autotest/sim_vehicle.py -v ArduPlane --custom-location="8.37074,77.36632,0,270" --console --map
```
