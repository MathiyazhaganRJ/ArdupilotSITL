# ARDUPILOT NAVIGATION GUIDE: GPS JAMMED, SPOOFED & DENIED ENVIRONMENTS
**Operational Flight Guide: Failure Cascades, EKF3 Navigation Mechanics & Safe Parameter Configuration**  
*Applicable Fleet: All ArduPilot Fixed-Wing, VTOL & Quadplane Platforms (EKF3 Inertial Core)*

---

## 1. Executive Summary & Threat Taxonomy

Operating unmanned aircraft in contested or electronically degraded airspace requires an understanding of how ArduPilot's Extended Kalman Filter (EKF3) and Attitude & Heading Reference System (AHRS) interact with corrupted sensor inputs. 

| Threat Regime | Mechanism & Physical Manifestation | Autopilot Vulnerability | Primary Countermeasure |
| :--- | :--- | :--- | :--- |
| **Electronic RF Jamming** | Broadband RF noise ($C/N_0 < 28\text{ dB-Hz}$) floods GPS antenna. GPS module **remains powered** and outputs degraded 3D fixes with jumping coordinates ($\pm 50\text{ to }400\text{ m/s}$ noise). | **DCM Fallback Hunting:** Autopilot drops to legacy DCM, feeding jumping coordinates directly into navigation, causing severe wandering/weaving. | Lock out DCM (`AHRS_OPTIONS = 3`) and prevent position reset (`EK3_OPTIONS = 1`). |
| **Adversarial GPS Spoofing** | Hostile terrestrial transmitters broadcast false ephemeris and pseudoranges to hijack aircraft position via coordinate step-jumps or deceptive drift. | **Trajectory Hijack:** Autopilot accepts false positions, deviating miles off course or flying into terrain. | Tighten horizontal gate (`EK3_GLITCH_RAD = 15`) and isolate attitude (`AHRS_GPS_USE = 0`). |
| **Total GPS Denial (Cutoff)** | Complete loss of satellite signals ($fix\_type = 0$, $sats = 0$) due to antenna severance, tunnel/canyon flight, or hardware cutoff (`SIM_GPS1_ENABLE = 0`). | **Positional Drift:** Aircraft drifts if horizontal wind is unknown or unmodelled. | Aerodynamic drag calibration (`EK3_DRAG_BCOEF_X/Y = 25`) and calibrated True Airspeed. |
| **Zero-Airspeed Hover Denial** | GPS denied while VTOL/quadplane is stationary in hover ($V_{\text{air}} \approx 0\text{ m/s}$). | **Hover Departure:** Pitot tube has no dynamic pressure; cannot compute aerodynamic wind vector. | Optical flow camera fusion (`FLOW_ENABLE = 1`, `EK3_SRC1_VELXY = 5`). |

---

## 2. Jammed Scenario Execution: Unconfigured vs. Configured

Understanding *why* an unconfigured drone wanders during jamming is essential for flight safety:

### The Failure Chain (Default / Unconfigured Autopilot)
```
[Broadband RF Jamming Enters Antenna]
                 │
                 ▼
[GPS Module Outputs Jumping Coordinates (Reports Status >= 3D Fix)]
                 │
                 ▼
[EKF3 Flags Innovation Anomaly (pos_horiz_ratio > 1.0) & Rejects GPS]
                 │
                 ▼
╔═════════════════════════════════════════════════════════════════════════════╗
║                      THE UNCONFIGURED FAILURE CASCADE                       ║
║                                                                             ║
║ 1. DCM Fallback Trap (AHRS_OPTIONS = 0):                                    ║
║    AP_AHRS detects EKF dropped GPS, but sees receiver status >= 3D.         ║
║    It automatically drops into legacy DCM (Direction Cosine Matrix).        ║
║    DCM has NO dead reckoning filter — it feeds raw jumping coordinates       ║
║    straight to L1 navigation! The plane violently banks left/right (hunting).║
║                                                                             ║
║ 2. Attitude Horizon Corruption (AHRS_GPS_USE = 1):                          ║
║    Centrifugal turn compensation uses erratic GPS velocities (V_gps).       ║
║    Artificial horizon tilts falsely, inducing severe wing-rocking.          ║
║                                                                             ║
║ 3. EKF Timeout Reset (EK3_OPTIONS = 0):                                     ║
║    After 5-10s of rejected GPS, EKF3 gives up and resets position directly  ║
║    onto corrupted GPS coordinates.                                          ║
╚═════════════════════════════════════════════════════════════════════════════╝
```

### The Safe Execution Chain (Properly Configured Autopilot)
```
[Broadband RF Jamming Enters Antenna]
                 │
                 ▼
[EKF3 Rejects Corrupted Coordinates at Innovation Gate (EK3_GLITCH_RAD = 15)]
                 │
                 ▼
[DCM Lockout Active (AHRS_OPTIONS = 3)]
  * Fallback to DCM is strictly forbidden.
  * Navigation remains locked inside EKF3 Dead Reckoning.
                 │
                 ▼
[Attitude Isolated (AHRS_GPS_USE = 0) & Timeout Reset Blocked (EK3_OPTIONS = 1)]
  * Artificial horizon remains level and rock-steady.
  * EKF3 holds dead reckoning indefinitely without resetting to noise.
                 │
                 ▼
[Aerodynamic Wind Dead Reckoning Engages Seamlessly]
  * Synthesizes ground track from True Airspeed (V_tas), Compass, and Drag-Modelled Wind (W).
  * Aircraft tracks planned mission waypoints smoothly with ZERO wandering.
```

---

## 3. Safe Parameter Configuration by Threat Regime

### Table 1: Electronic Warfare RF Jamming Countermeasures
Configure these parameters to isolate the navigation filter and prevent the aircraft from chasing jumping coordinates:

| Parameter | Default Value | Anti-Jam Value | Threat Addressed | Operational Function & Technical Mechanism | SITL / MAVLink Console Command |
| :--- | :---: | :---: | :--- | :--- | :--- |
| **`AHRS_OPTIONS`** | `0` | **`3`** | RF Jamming Hunting | **DCM Lockout:** Bit 0 (Plane) + Bit 1 (VTOL). Inhibits automatic fallback to legacy DCM when GPS reports degraded 3D fix. Eliminates left-right wandering. | `param set AHRS_OPTIONS 3` |
| **`EK3_OPTIONS`** | `0` | **`1`** | Position Reset Trap | **Jamming Expected:** Bit 0 (`JammingExpected`). Prevents EKF3 from automatically resetting its position to bad GPS upon timeout; locks EKF in Dead Reckoning. | `param set EK3_OPTIONS 1` |
| **`AHRS_GPS_USE`** | `1` | **`0`** | Wing-Rocking / Tilt | **Attitude Isolation:** Disconnects GPS ground velocity from centrifugal turn compensation ($a_{\text{cent}} = \omega_z \cdot V_{\text{gps}}$). Keeps horizon true. | `param set AHRS_GPS_USE 0` |

---

### Table 2: Adversarial GPS Spoofing & Innovation Step Gating
Configure these parameters to detect and immediately reject malicious coordinate step-jumps injected by terrestrial spoofers:

| Parameter | Default Value | Anti-Spoof Value | Threat Addressed | Operational Function & Technical Mechanism | SITL / MAVLink Console Command |
| :--- | :---: | :---: | :--- | :--- | :--- |
| **`EK3_GLITCH_RAD`** | `25.0` m | **`15.0` to `20.0` m** | Trajectory Hijacking | **Step-Jump Gate:** Maximum allowable horizontal coordinate jump between consecutive GPS updates before EKF rejects it as anomalous. | `param set EK3_GLITCH_RAD 15` |
| **`GPS_GNSS_MODE`** | `0` | **`65`** *(GPS+GAL+GLO)* | Single-Band Spoofing | **Multi-Constellation Diversity:** Forces receiver to track multiple GNSS constellations simultaneously, increasing spoofing resistance. | `param set GPS_GNSS_MODE 65` |

---

### Table 3: Total GPS Denial & Aerodynamic Wind Dead Reckoning (Fixed-Wing)
When GPS signal is completely lost, EKF3 uses aerodynamic drag ballistics and airspeed to navigate:

| Parameter | Default Value | Dead Reckoning Value | Threat Addressed | Operational Function & Technical Mechanism | SITL / MAVLink Console Command |
| :--- | :---: | :---: | :--- | :--- | :--- |
| **`EK3_DRAG_BCOEF_X`** | `0.0` | **`25.0` to `35.0`** | Wind Drift | **Longitudinal Drag Ballistics:** Calibrates fuselage drag ($kg/m^2$). Allows EKF3 to estimate wind vector from accelerometer drag vs airspeed. | `param set EK3_DRAG_BCOEF_X 25` |
| **`EK3_DRAG_BCOEF_Y`** | `0.0` | **`25.0` to `35.0`** | Crosswind Drift | **Lateral Drag Ballistics:** Calibrates airframe side-slip drag. Computes crosswind crab angle ($\beta$) to hold ground track in gusts. | `param set EK3_DRAG_BCOEF_Y 25` |
| **`ARSPD_USE`** | `1` | **`1`** | Speed Loss | **Airspeed Sensor Mandatory:** Pitot true airspeed ($V_{\text{tas}}$) is required to calculate $\vec{V}_{\text{ground}} = \vec{V}_{\text{air}} + \vec{W}$. | `param set ARSPD_USE 1` |
| **`COMPASS_USE`** | `1` | **`1`** | Heading Drift | **Compass Fusion:** Accurately calibrated magnetometer is required to project true airspeed vector onto geographic North/East frame. | `param set COMPASS_USE 1` |

---

### Table 4: VTOL & Hover Optical Flow Fallback (Zero Forward Airspeed)
During hover or vertical takeoff/landing, forward airspeed is zero ($V_{\text{air}} = 0$). Optical flow camera fusion must provide horizontal velocity:

| Parameter | Default Value | Hover Fallback Value | Threat Addressed | Operational Function & Technical Mechanism | SITL / MAVLink Console Command |
| :--- | :---: | :---: | :--- | :--- | :--- |
| **`FLOW_ENABLE`** | `0` | **`1`** | Hover Drift | **Sensor Activation:** Enables downward-pointing optical flow camera driver. (In SITL: `SIM_FLOW_ENABLE = 1`). | `param set SIM_FLOW_ENABLE 1` |
| **`EK3_FLOW_USE`** | `1` | **`1`** | Velocity Loss | **EKF Flow Fusion:** Directs EKF3 to ingest pixel displacement rates ($rad/s$) to observe horizontal ground speed. | `param set EK3_FLOW_USE 1` |
| **`EK3_SRC1_VELXY`** | `3` (GPS) | **`5`** (Flow) | Horizontal Wander | **Primary Velocity Source:** Sets Optical Flow as primary horizontal velocity source during GPS denial. | `param set EK3_SRC1_VELXY 5` |

---

## 4. Master Parameter Quick-Reference Table

Use this comprehensive table as a single-page cockpit cheat sheet:

| # | Parameter | Default | Safe Target | Threat Scope | Core Purpose | Single-Line Command |
| :---: | :--- | :---: | :---: | :--- | :--- | :--- |
| **1** | `AHRS_OPTIONS` | `0` | **`3`** | Jamming | Inhibits DCM fallback; stops coordinate hunting | `param set AHRS_OPTIONS 3` |
| **2** | `EK3_OPTIONS` | `0` | **`1`** | Jamming | Prevents EKF timeout reset to degraded GPS | `param set EK3_OPTIONS 1` |
| **3** | `AHRS_GPS_USE` | `1` | **`0`** | Jamming / Spoofing | Isolates horizon from erratic GPS velocities | `param set AHRS_GPS_USE 0` |
| **4** | `EK3_GLITCH_RAD` | `25.0` | **`15.0`** | Spoofing | Rejects coordinate step-jumps $> 15\text{ m}$ | `param set EK3_GLITCH_RAD 15` |
| **5** | `EK3_DRAG_BCOEF_X` | `0.0` | **`25.0`** | No-GPS Cruise | Airframe drag model for wind speed estimation | `param set EK3_DRAG_BCOEF_X 25` |
| **6** | `EK3_DRAG_BCOEF_Y` | `0.0` | **`25.0`** | No-GPS Cruise | Crosswind crab angle and side-slip compensation | `param set EK3_DRAG_BCOEF_Y 25` |
| **7** | `ARSPD_USE` | `1` | **`1`** | No-GPS Cruise | Provides true airspeed ($V_{\text{tas}}$) for dead reckoning | `param set ARSPD_USE 1` |
| **8** | `SIM_FLOW_ENABLE` | `0` | **`1`** | No-GPS Hover | Enables optical flow camera in SITL simulation | `param set SIM_FLOW_ENABLE 1` |
| **9** | `EK3_SRC1_VELXY` | `3` | **`5`** | No-GPS Hover | Sets Optical Flow as velocity source in hover | `param set EK3_SRC1_VELXY 5` |

### One-Shot Anti-Jam Terminal Script
Copy and paste this script directly into MAVProxy, SITL, or Mission Planner terminal:
```bash
param set AHRS_OPTIONS 3
param set EK3_OPTIONS 1
param set AHRS_GPS_USE 0
param set EK3_GLITCH_RAD 15
param set EK3_DRAG_BCOEF_X 25
param set EK3_DRAG_BCOEF_Y 25
param set ARSPD_USE 1
```

---

## 5. Standard Operating Procedure (SOP) Protocol

### Phase 1: Pre-Flight Parameter Verification
1. Ensure `ARSPD_ENABLE = 1` and conduct pitot blow-check to verify healthy airspeed response ($\pm 1.0\text{ m/s}$).
2. Verify compass calibration quality ($fit\_error < 2.0$) and valid magnetic declination.
3. Upload the One-Shot Anti-Jam Parameter Block.

### Phase 2: Mandatory Wind-Learning Orbit (The Golden Rule)
> **CRITICAL RULE:** Dead reckoning relies on the wind triangle: $\vec{V}_{\text{ground}} = \vec{V}_{\text{air}} + \vec{W}_{\text{wind}}$.  
> If an aircraft penetrates an electronic warfare zone *immediately* after takeoff without learning the wind, it will drift proportional to prevailing wind velocity.

1. After takeoff, climb to cruise altitude (50–100 m AGL) in clear GPS coverage.
2. Enter **`AUTO` turns** or fly in **`LOITER` for 20 to 30 seconds**.
3. Allow EKF3 to compare pitot airspeed against GPS ground track across $360^\circ$ of heading. EKF3 will converge the horizontal wind state vector ($\vec{W}$).
4. Once wind speed and direction in telemetry are steady, proceed into the mission area.

### Phase 3: Contested Zone Ingress & Monitoring
1. When jamming or spoofing occurs, observe MAVLink `STATUSTEXT`:
   - `GPS_Glitch: pos step` or `EKF3: pos timeout` is normal and expected.
   - Confirm aircraft maintains wings-level attitude and continues straight along waypoint track without weaving.
2. In the Cockpit Visualizer / GCS:
   - Annunciator will display `DR · ±XXm (Dead Reckoning)`.
   - The circular position uncertainty ring will expand at $\approx 1.2\text{ m/s}$, reflecting un-aided inertial drift.

### Phase 4: Egress & GPS Recovery
1. When exiting the jammed environment and GPS signals re-stabilize:
2. EKF3 automatically monitors innovation ratios. Once GPS coordinates remain within the innovation gate for 3–5 seconds continuously:
   - `pos_horiz_abs` transitions back to `VALID`.
   - Position uncertainty collapses back to satellite accuracy ($< 1.5\text{ m}$).
   - Re-enable attitude GPS aiding if desired: `param set AHRS_GPS_USE 1`.
