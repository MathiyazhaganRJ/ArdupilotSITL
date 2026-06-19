# Adding Custom 3D Models to ArduPilot SITL Visualizer

This guide explains how to export an aircraft from **OpenVSP**, convert it into a web-friendly `.glb` format, and integrate it into the 3D visualizer so that the propellers match your specific airframe geometry.

## 1. Export from OpenVSP
1. Open your aircraft model in OpenVSP.
2. Go to **File -> Export...**
3. Select **Wavefront OBJ (*.obj)**.
4. Save the file (e.g., `Endurance.obj`).

## 2. Convert OBJ to GLB
The visualizer uses the efficient `.glb` (glTF binary) format for 3D models. We have provided a Python conversion script that handles the coordinate system mapping and geometry packing.

1. Copy your `Endurance.obj` file into the `visualizer/models/` directory.
2. Open a terminal in that directory and run the conversion script:
   ```powershell
   cd ArdupilotSITL/visualizer/models
   python convert_obj_to_glb.py
   ```
   *(Note: You must have `pygltflib` and `numpy` installed: `pip install pygltflib numpy`)*
3. The script will output the wingspan and length of your aircraft. **Write these numbers down**, as you will need them to place the propellers in the code.
4. The script will generate an `Endurance.glb` file.

## 3. Update the Visualizer Code
Open `visualizer/index.html` in your code editor. Around line 375, you will find the `AIRCRAFT GEOMETRY CONFIGURATION` block. You do not need to dig through the code; simply change the values in this single block to configure your entire aircraft!

```javascript
// ==========================================
// AIRCRAFT GEOMETRY CONFIGURATION
// ==========================================
const CONFIG = {
    modelFile: 'models/YourNewModel.glb', // Change to your .glb file name
    modelColor: 0xff5500,                 // Hex color for the airplane body
    
    // CRUISE PROPELLERS (Pusher & Twin)
    cruisePropDia: 0.3,                     // Diameter of forward-flight props
    pusherPos: { x: 0, y: -0.05, z: 0.45 }, // z: 0.45 places it roughly on a 0.9m tail
    
    // TWIN ENGINES
    twinPosL: { x: -0.4, y: 0.05, z: -0.15 }, // Left nacelle
    twinPosR: { x: 0.4, y: 0.05, z: -0.15 },  // Right nacelle
    
    // VTOL QUAD MOTORS
    vtolPropDia: 0.3, // Diameter of quadplane lift props
    vtolBoomY: -0.08, // Negative value mounts the boom beneath the wing
    vtolArmX: 0.5,    // Distance from centerline to the left/right booms
    vtolMotorZ: 0.35  // Distance from CG to the front/rear motors. 
                      // Note: The carbon boom length automatically scales to fit this!
};
// ==========================================
```

### Coordinate System Cheat Sheet:
- **X-axis (Width):** `+X` is the right wing, `-X` is the left wing.
- **Y-axis (Height):** `+Y` is up, `-Y` is down (under the wing).
- **Z-axis (Length):** `-Z` is the nose, `+Z` is the tail.

## 4. Test It
Start the visualizer server from the root directory:
```powershell
python server/server.py
```
This script will automatically start the websocket bridge, the web server, and open your browser! Start ArduPilot SITL and verify that the propellers rotate correctly relative to the new 3D model.
