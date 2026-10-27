# ArdupilotSITL

A real-time web visualizer and MAVLink telemetry bridge for ArduPilot Software-In-The-Loop (SITL) simulation.

## Repository Structure

```
ArdupilotSITL/
├── visualizer/                  # Three.js / CesiumJS web frontend
│   ├── index.html               # Main 3D SITL visualizer
│   └── models/                  # 3D aircraft models (.glb / .gltf)
│       └── <your_plane>.glb     # OpenVSP exported & converted model
├── server/
│   └── server.py                # MAVLink → WebSocket bridge (Python)
├── docs/                        # Documentation and guides
│   ├── JSBSIM_GUIDE.md
│   └── ardupilot_build_cheatsheet.md
├── .gitignore
└── README.md
```

## How It Works

```
ArduPilot SITL  →  MAVLink (UDP)  →  server.py  →  WebSocket  →  index.html (Browser)
```

To make the visualizer work seamlessly, `server.py` runs **two servers simultaneously** in the background:

1. **MAVLink WebSocket Bridge (`ws://127.0.0.1:8766`)**: This server connects to ArduPilot's UDP stream to read raw MAVLink telemetry (attitude, GPS, servo PWM outputs). It decodes this binary data, converts it into lightweight JSON, and broadcasts it over WebSockets so the Javascript in your browser can animate the 3D model in real-time.
2. **HTTP Web Server (`http://127.0.0.1:8000`)**: Modern web browsers have strict security rules (CORS) that block 3D models (`.glb` files) from loading if you just double-click an HTML file on your hard drive (`file:///...`). This built-in HTTP server hosts the `visualizer` folder locally, bypassing those restrictions and allowing `Three.js` to securely load the aircraft meshes and textures.

### Workflow
1. Start ArduPilot SITL (with JSBSim backend)
2. Run `python server/server.py`
3. The script will automatically open your default browser to the visualizer!
4. Watch your aircraft fly live in 3D!

## Requirements & Installation

### Python Packages (All Platforms)

```bash
pip install -r requirements.txt
```

### Ubuntu / Debian / WSL (Native Desktop Window Requirements)

To run the standalone native desktop application window via GTK/WebKit2:

```bash
# Automated setup:
chmod +x setup_ubuntu.sh
./setup_ubuntu.sh

# Or manual apt install:
sudo apt update
sudo apt install -y python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1
# (Use gir1.2-webkit2-4.0 if running Ubuntu 20.04 LTS)
```

> **Note for WSL**: If running without desktop GUI extensions, the server automatically runs in headless mode and pops open your default Windows browser tab, or you can explicitly run with `python server/server.py --headless`.

---

## Quick Start

### 1. Start ArduPilot SITL (WSL / Linux)
```bash
sim_vehicle.py -v ArduPlane -f jsbsim:SharkHawk --out=udp:127.0.0.1:14551
```

### 2. Start the Telemetry Bridge & Visualizer

- **Standalone Native Desktop App**:
  ```bash
  python server/server.py
  ```
- **Headless Server Mode** (opens as a browser tab):
  ```bash
  python server/server.py --headless
  ```

### 3. ArduPilot DataFlash Log Viewer
To inspect `.bin` and `.tlog` flight logs offline in 3D:
```bash
python log_viewer.py
```

---

## Adding a Custom 3D Model (OpenVSP)

1. Export your OpenVSP geometry as `.OBJ` or `.STL`
2. Convert to `.glb` using [Blender](https://www.blender.org/) or an [online converter](https://www.npmjs.com/package/gltf-pipeline)
3. Place the `.glb` file in `visualizer/models/`
4. Update the model path in `visualizer/index.html`

> **Note:** `.glb` files are gitignored (too large). Use [Git LFS](https://git-lfs.github.com/) if you need to track them.

## Related Repo

- [JSBSim-Ardupilot](https://github.com/MathiyazhaganRJ/JSBSim-Ardupilot) — Flight physics engine and aircraft XML definitions

