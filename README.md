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
