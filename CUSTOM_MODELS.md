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
Open `visualizer/index.html` in your code editor and make the following changes:

### A. Load the New Model
Find the `GLTFLoader` section (around line 228) and update the file path to your new `.glb` file:
```javascript
loader.load('models/YourModel.glb', function(gltf) {
    const model = gltf.scene;
    
    // OpenVSP uses a different coordinate system. This rotates it so the nose points forward.
    model.rotation.y = -Math.PI / 2; 

    model.traverse(function(child) {
        if(child.isMesh) {
            child.geometry.computeVertexNormals(); // Generates lighting reflections
            child.material = new THREE.MeshStandardMaterial({
                color: 0xff5500, // Vibrant Orange (Change this hex code for different colors)
                roughness: 0.4,
                metalness: 0.3,
                side: THREE.DoubleSide
            });
        }
    });
    aeroGroup.add(model);
});
```

### B. Adjust Propeller Positions
Based on the dimensions printed during the Python conversion step, you will need to adjust the X, Y, Z coordinates for your propellers.
- **X-axis:** Left/Right (Wingspan). `+X` is the right wing, `-X` is the left wing.
- **Y-axis:** Up/Down. `+Y` is up.
- **Z-axis:** Forward/Backward (Length). `-Z` is the nose, `+Z` is the tail.

**Cruise Propeller (Pusher)**
Find `pusherProp.position.set(...)`. If your plane has a length of 0.9m, the tail is roughly at `Z = 0.45`.
```javascript
pusherProp.position.set(0, 0, 0.45); // Adjust Z to sit exactly on the tail
```

**VTOL Quadplane Propellers**
Find the `armPositions` array. Adjust the X and Z values to place the quad rotors correctly on your wings.
```javascript
const armPositions = [
    { x: 0.5, z: -0.35 }, // Front Right
    { x: -0.5, z: 0.35 }, // Back Left
    { x: 0.5, z: 0.35 },  // Back Right
    { x: -0.5, z: -0.35 } // Front Left
];
```

**Twin Engine Propellers**
If using a twin-engine layout, find `twinMotorL` and `twinMotorR` and adjust their `X` coordinates to match the location of the engine nacelles on the wings.

## 4. Test It
Start your local Python web server in the `visualizer` folder:
```powershell
python -m http.server 8000
```
Open `http://localhost:8000` in your browser. Start ArduPilot SITL and verify that the propellers rotate correctly relative to the new 3D model!
