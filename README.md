# ArduPilot SITL 3D Web Visualizer

A high-performance, real-time 3D flight visualizer for **ArduPilot SITL** (Software In The Loop). Built specifically for evaluating custom VTOL, Fixed Wing, and Twin Engine drone designs (like the Shark Hawk E+). 

Designed by RJ.

## ✨ Features
* **60 FPS Buttery-Smooth Rendering**: Uses advanced LERP (position) and SLERP (rotation) low-pass filtering to convert 30Hz jittery MAVLink network packets into fluid 60FPS browser animations.
* **Multiple Vehicle Configurations**: Instantly switch the 3D model between:
  * QuadPlane (VTOL)
  * Standard Fixed Wing (Pusher)
  * Twin Engine Fixed Wing
  * Quadcopter
* **Dynamic Motor Mapping**: Change which PWM channel drives which 3D propeller directly from the UI. Supports ArduPilot's standard Quad-X mapping (Motor 1=FR, Motor 2=BL, etc.).
* **Live Telemetry Dashboard**: Displays Firmware (ArduPlane/ArduCopter), Flight Mode, Altitude, Airspeed, Ground Speed, and raw PWM output bars.
* **3D Flight Path Trail**: Draws a continuous 3D green trail mapping your flight trajectory.
* **Apple-Style UI**: A clean, modern, glassmorphic dashboard with a seamless **Light/Dark Mode** toggle.

## 🛠️ Prerequisites
* Python 3.8+
* ArduPilot SITL (running locally or in WSL)

Install the required Python packages:
```bash
pip install pymavlink websockets
```

## 🚀 How to Run

1. **Start ArduPilot SITL**:
   Launch your SITL simulation and ensure MAVLink is being routed to UDP port `14555` on localhost.
   *(If you are using Mission Planner, you can use the "MAVLink Mirror" feature to forward telemetry to `127.0.0.1:14555`).*

   Example WSL Quadplane start command:
   ```bash
   Tools/autotest/sim_vehicle.py -v ArduPlane -f quadplane --console --map
   ```

2. **Start the WebSocket Bridge**:
   Open a terminal in this directory and run the Python bridge server. This script listens for MAVLink packets and translates them into WebSocket JSON packets.
   ```bash
   python server.py
   ```

3. **Open the Visualizer**:
   Simply double-click `index.html` to open it in Google Chrome or Mozilla Firefox. 
   *(No web server required!)*

## 🧠 Architecture
1. **`server.py`**: A lightweight Python asynchronous bridge using `pymavlink`. It connects to SITL via UDP, requests high-speed `ATTITUDE`, `LOCAL_POSITION_NED`, `VFR_HUD`, and `SERVO_OUTPUT_RAW` streams, and relays them to connected web clients via WebSockets.
2. **`index.html`**: A pure HTML/JS frontend utilizing **Three.js** for WebGL rendering. It manages the 3D scene, vehicle geometry generation, camera follow logic, and dynamically updates the DOM dashboard.

## 🔮 Future Development
- [ ] Add Gamepad API support to fly SITL using an Xbox/PlayStation controller from the browser.
- [ ] Implement live scrolling PID tuning graphs.
- [ ] Add GLTFLoader to allow dropping in custom CAD `.glb` models (e.g. Shark Hawk E+).
- [ ] Animate control surfaces (Ailerons, Elevator, Rudder) using `SERVO_RAW` telemetry.
