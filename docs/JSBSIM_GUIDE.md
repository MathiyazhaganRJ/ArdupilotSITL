# How to Port Your Airplane into JSBSim for ArduPilot SITL
## Step-by-Step Guide from Zero

---

## STEP 1: Gather Your Airplane's Physical Data

Before touching any files, collect these numbers from your design or measurements.

**Geometry:**
- Wing Span (meters)
- Wing Area (m²)
- Mean Aerodynamic Chord / MAC (meters)
- Empty Weight (kg)
- CG location from nose (meters)

**Aerodynamics (from XFLR5 or Traub equations):**
- Lift Curve Slope: CLα (per radian, typically ~4.5–5.5)
- Zero-Lift Angle of Attack: α0 (degrees, typically -2° to -4°)
- Zero-Lift Drag Coefficient: CD0 (typically 0.02–0.04)
- Oswald efficiency factor: e (typically 0.75–0.85)
- Aspect Ratio: AR = span² / area

**Propulsion:**
- Motor Kv (RPM/V)
- Battery Voltage (V)
- Propeller diameter and pitch (e.g., 15x10)
- Max Thrust (grams or Newtons)
- Max Current Draw (Amps)

---

## STEP 2: Set Up Your Model Folder

Navigate to your ArduPilot directory in WSL and copy the Rascal template as your starting point.

```bash
cd ~/ardupilot
cp -r Tools/autotest/aircraft/Rascal Tools/autotest/aircraft/MyPlane
```

Rename all files inside the folder from "Rascal" to "MyPlane":
```bash
cd Tools/autotest/aircraft/MyPlane
rename 's/Rascal/MyPlane/g' *
```

---

## STEP 3: Edit the Main Physics File (`MyPlane.xml`)

Open the file in a text editor:
```bash
nano ~/ardupilot/Tools/autotest/aircraft/MyPlane/MyPlane.xml
```

### 3a. Update Physical Dimensions (around line 15)
Convert your metric measurements to imperial (JSBSim uses feet and pounds):
- Meters to Feet: multiply by **3.281**
- m² to ft²: multiply by **10.764**
- kg to lbs: multiply by **2.205**

```xml
<metrics>
    <wingarea  unit="FT2">  YOUR_WING_AREA_FT2  </wingarea>
    <wingspan  unit="FT">   YOUR_WINGSPAN_FT    </wingspan>
    <chord     unit="FT">   YOUR_CHORD_FT       </chord>
    <htailarea unit="FT2">  2.0                 </htailarea>
    <htailarm  unit="FT">   4.0                 </htailarm>
    <vtailarea unit="FT2">  1.0                 </vtailarea>
    <vtailarm  unit="FT">   4.0                 </vtailarm>
</metrics>
```

### 3b. Update Mass and Inertia (around line 40)
```xml
<mass_balance>
    <emptywt unit="LBS"> YOUR_EMPTY_WEIGHT_LBS </emptywt>
    <location name="CG" unit="IN">
        <x> YOUR_CG_FROM_NOSE_INCHES </x>
        <y> 0 </y>
        <z> 0 </z>
    </location>
    <!-- Moments of Inertia: estimate using Ixx=mass*span²/12 -->
    <ixx unit="SLUG*FT2"> 0.5 </ixx>
    <iyy unit="SLUG*FT2"> 1.0 </iyy>
    <izz unit="SLUG*FT2"> 1.3 </izz>
</mass_balance>
```

### 3c. Update Aerodynamic Coefficients (around line 200)

**Lift:**
```xml
<function name="aero/coefficient/CLalpha">
    <description>Lift_curve_slope</description>
    <product>
        <property>aero/qbar-psf</property>
        <property>metrics/Sw-sqft</property>
        <property>aero/alpha-rad</property>
        <value> YOUR_CL_ALPHA </value>   <!-- e.g., 5.0 per radian -->
    </product>
</function>
```

**Zero-lift Drag (CD0):**
```xml
<function name="aero/coefficient/CD0">
    <description>Minimum_drag_coefficient</description>
    <product>
        <property>aero/qbar-psf</property>
        <property>metrics/Sw-sqft</property>
        <value> YOUR_CD0 </value>   <!-- e.g., 0.028 -->
    </product>
</function>
```

---

## STEP 4: Edit the Propulsion (Engine + Propeller)

The engine files are inside: `Tools/autotest/aircraft/MyPlane/Engines/`

### 4a. Motor File (e.g., `electric_motor.xml`)
Change the max thrust and voltage to match your motor+prop combination:
```xml
<thruster file="propeller">
    <sense> 1 </sense>
    <location unit="IN">
        <x> -40 </x>  <!-- forward of CG -->
        <y>  0  </y>
        <z>  0  </z>
    </location>
    <orient unit="DEG">
        <roll>  0 </roll>
        <pitch> 0 </pitch>
        <yaw>   0 </yaw>
    </orient>
    <p_factor> 0.0 </p_factor>
</thruster>
```

### 4b. Propeller File
The propeller file contains a table of Thrust Coefficient (CT) vs advance ratio (J).
You can get these values from the **APC Propeller Performance Data** website:
https://www.apcprop.com/technical-information/performance-data/

Download the data for your 15x10 prop and copy the CT/CP vs J table into the XML.

---

## STEP 5: Register Your Model in ArduPilot

Open the vehicle registry file:
```bash
nano ~/ardupilot/Tools/autotest/pysim/vehicleinfo.py
```

Find the `"jsbsim:Rascal"` block and add a similar block for your plane right after it:
```python
"jsbsim:MyPlane": {
    "model": "MyPlane",
    "start-altitude": 0,
},
```

---

## STEP 6: Run Your Custom Model

```bash
Tools/autotest/sim_vehicle.py -v ArduPlane -f jsbsim:MyPlane -w --console --map
```

> The `-w` flag wipes old parameters. Always use it the first time you launch a new model.

---

## STEP 7: Validate Your Model

Once it's running, connect Mission Planner to `127.0.0.1:14550` and check:

1. **Trim speed:** Put in FBWA mode. The plane should fly level without elevator input at your designed cruise speed (~18 m/s for Shark Hawk E+).
2. **Current Draw:** Should be ~5A at cruise speed.
3. **Stall Speed:** Reduce throttle slowly. The plane should stall at your calculated stall speed.
4. **Roll/Pitch response:** Should feel like a real plane, not twitchy or sluggish.

If anything feels wrong, go back to `MyPlane.xml` and tweak the aerodynamic coefficients.

---

## Useful References

- JSBSim Reference Manual: https://jsbsim-team.github.io/jsbsim-reference-manual/
- APC Propeller Data: https://www.apcprop.com/technical-information/performance-data/
- ArduPilot SITL Docs: https://ardupilot.org/dev/docs/sitl-simulator-software-in-the-loop.html
- XFLR5 (for generating your CLα and CD0): https://www.xflr5.tech/xflr5.htm
