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

1. Start ArduPilot SITL (with JSBSim backend)
2. Run `server/server.py` to bridge MAVLink UDP → WebSocket
3. Open `visualizer/index.html` in your browser
4. Watch your aircraft fly live in 3D!

## Quick Start

```bash
# 1. Start ArduPilot SITL (in WSL/Linux)
sim_vehicle.py -v ArduPlane -f jsbsim:SharkHawk --out=udp:127.0.0.1:14551

# 2. Start the MAVLink bridge
python server/server.py

# 3. Open the visualizer
# Open visualizer/index.html in your browser
```

## Adding a Custom 3D Model (OpenVSP)

1. Export your OpenVSP geometry as `.OBJ` or `.STL`
2. Convert to `.glb` using [Blender](https://www.blender.org/) or an [online converter](https://www.npmjs.com/package/gltf-pipeline)
3. Place the `.glb` file in `visualizer/models/`
4. Update the model path in `visualizer/index.html`

> **Note:** `.glb` files are gitignored (too large). Use [Git LFS](https://git-lfs.github.com/) if you need to track them.

## Related Repo

- [JSBSim-Ardupilot](https://github.com/MathiyazhaganRJ/JSBSim-Ardupilot) — Flight physics engine and aircraft XML definitions

## Requirements

- Python 3.8+ with `pymavlink` and `websockets`
- Modern web browser (Chrome/Firefox)
