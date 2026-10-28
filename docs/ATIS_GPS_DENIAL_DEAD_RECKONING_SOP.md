# ATIS BROADCAST INFORMATION BRAVO // AVIONICS SCENARIO FLIGHT EXECUTION MANUAL
**Station:** `VAPO SITL`  
**Fleet:** `ArduPilot EKF3 Fixed-Wing & VTOL Fleet`  
**Operational Directive:** `GPS Denial, Electronic Jamming, Spoofing Gating & Dead Reckoning Protocols`  
**Instruction:** `Execute parameters via Cockpit MCDU Line Select Keys or SITL Console`  

---

```
================================================================================
ATIS BROADCAST INFORMATION BRAVO // AVIONICS SCENARIO FLIGHT EXECUTION DIRECTIVE
STATION: VAPO SITL | FLEET: ARDUPILOT EKF3 FIXED-WING & VTOL AIRCRAFT
OPERATIONAL DIRECTIVE: GPS DENIAL, ELECTRONIC JAMMING, SPOOFING GATING & DEAD RECKONING
================================================================================
```

---

# PART I: Avionics Parameter Technical Reference

## 1. GNSS Denial, Hardware Cutoff & Jamming Simulation

### `SIM_GPS1_ENABLE`
- **Type:** SITL Hardware Toggle
- **Default:** `1` (Active) $\rightarrow$ **Execution Target:** `0` (Severed / Denied)
- **MCDU / Console Command:**  
  ```bash
  param set SIM_GPS1_ENABLE 0
  ```
- **Description:**  
  Simulates complete power cutoff or physical antenna severance to the primary GNSS receiver. When set to `0`, SITL instantly halts satellite tracking, dropping MAVLink `GPS_RAW_INT` to $fix\_type = 0$ (No GPS) and $satellites\_visible = 0$. This forces the ArduPilot EKF3 core to declare horizontal position invalid and transition immediately into inertial Dead Reckoning mode without coordinate jitter.

---

### `SIM_GPS1_JAM`
- **Type:** SITL Electronic Warfare Injection
- **Default:** `0` (Normal RF) $\rightarrow$ **Execution Target:** `1` (RF Jammed)
- **MCDU / Console Command:**  
  ```bash
  param set SIM_GPS1_JAM 1
  ```
- **Description:**  
  Injects broadband RF interference and noise across GPS L1/L2 carrier frequencies. Receiver $C/N_0$ drops below the tracking threshold ($< 28\text{ dB-Hz}$), causing carrier phase lock loss, satellite drops, and severe HDOP inflation ($> 4.5$).  
  **Caution:** In SITL, the receiver retains a degraded 3D fix with jumping coordinates; requires automated gating configuration (Section 2) to prevent aircraft wandering.

---

## 2. GNSS Spoofing Defense, Innovation Gating & Attitude Protection

### `EK3_GLITCH_RAD`
- **Type:** EKF3 Innovation Step Gate Threshold
- **Default:** `25.0` m $\rightarrow$ **Recommended Anti-Jam Setting:** `15.0` to `20.0` m
- **MCDU / Console Command:**  
  ```bash
  param set EK3_GLITCH_RAD 15
  ```
- **Description:**  
  Defines the maximum horizontal step distance (in meters) allowed between consecutive GPS updates before EKF3 rejects the measurement as an anomaly. Rejects abrupt spoofed position jumps and extreme jamming noise spikes.

---

### `FS_EKF_THRESH`
- **Type:** Flight Safety Failsafe Threshold
- **Default:** `0.80` $\rightarrow$ **Anti-Jam Defensive Setting:** `0.60` to `0.65`
- **MCDU / Console Command:**  
  ```bash
  param set FS_EKF_THRESH 0.60
  ```
- **Description:**  
  Normalized innovation variance threshold triggering the autonomous EKF Failsafe. Lowering this threshold to `0.60` forces ArduPlane to trip the failsafe immediately under jamming noise rather than tolerating noisy jumping fixes.

---

### `AHRS_GPS_USE`
- **Type:** Attitude Filter Sensor Isolation
- **Default:** `1` (Enabled) $\rightarrow$ **Hostile RF Target:** `0` (Isolate AHRS from GPS)
- **MCDU / Console Command:**  
  ```bash
  param set AHRS_GPS_USE 0
  ```
- **Description:**  
  Disconnects GPS ground velocity from attitude centrifugal turn compensation ($a_{\text{cent}} = \omega_z \cdot V_{\text{gps}}$). Prevents erratic GPS velocity spikes from corrupting the artificial horizon and inducing violent wing-rocking.

---

## 3. Dead Reckoning \& Wind Estimation Configuration

### `EK3_DRAG_BCOEF_X` & `EK3_DRAG_BCOEF_Y`
- **Type:** Aerodynamic Ballistic Drag Coefficients ($kg/m^2$)
- **Default:** `0.0` (Disabled) $\rightarrow$ **Airframe Target:** `25.0` to `35.0`
- **MCDU / Console Commands:**  
  ```bash
  param set EK3_DRAG_BCOEF_X 25
  param set EK3_DRAG_BCOEF_Y 25
  ```
- **Description:**  
  Calibrates longitudinal and lateral airframe drag. In GPS-denied forward flight, EKF3 uses this coefficient along with pitot true airspeed ($V_{\text{tas}}$) and accelerometer deceleration to estimate the horizontal wind vector ($\vec{W}_{\text{wind}}$), establishing ground track: $\vec{V}_{\text{ground}} = \vec{V}_{\text{air}} + \vec{W}_{\text{wind}}$.

---

### `EK3_SRC_OPTIONS`
- **Type:** Sensor Fallback Bitmask
- **Default:** `0` (Manual Fallback) $\rightarrow$ **Autonomous Target:** `1` (Auto Fallback)
- **MCDU / Console Command:**  
  ```bash
  param set EK3_SRC_OPTIONS 1
  ```
- **Description:**  
  Bitmask parameter that enables automatic internal fallback switching. Setting Bit 0 allows EKF3 to drop an unhealthy GPS autonomously and switch to Dead Reckoning or Optical Flow without pilot intervention.

---

## 4. Optical Flow Sensor Simulation & Hover Velocity Fusion

### `SIM_FLOW_ENABLE`
- **Type:** SITL Optical Flow Hardware Simulation
- **Default:** `0` (Disabled) $\rightarrow$ **Execution Target:** `1` (Hardware Simulated)
- **MCDU / Console Command:**  
  ```bash
  param set SIM_FLOW_ENABLE 1
  ```

### `EK3_FLOW_USE` & `EK3_SRC1_VELXY`
- **MCDU / Console Commands:**  
  ```bash
  param set EK3_FLOW_USE 1
  param set EK3_SRC1_VELXY 5
  ```
- **Description:**  
  Instructs EKF3 to ingest optical flow angular velocity measurements into the navigation state vector. Setting `EK3_SRC1_VELXY = 5` directs EKF3 to use Optical Flow as the primary horizontal velocity reference, completely decoupling velocity estimation from satellite signals.

---

## 5. Environmental Wind & Atmospheric Turbulence Injection

### `SIM_WIND_SPD` / `SIM_WIND_DIR` / `SIM_WIND_TURB`
- **MCDU / Console Commands:**  
  ```bash
  param set SIM_WIND_SPD 12.0
  param set SIM_WIND_DIR 270
  param set SIM_WIND_TURB 0.25
  ```
- **Description:**  
  Controls SITL atmospheric wind speed, compass direction, and Dryden gust turbulence for realistic evaluation of aircraft drift compensation and crab angle computation.

---

# PART II: Tactical Flight Scenario Execution Protocols

---

## SCENARIO 1: Total GPS Denial / Hardware Cutoff (Clean Dead Reckoning)

* **Operational Objective:** Evaluate pure aerodynamic and inertial dead reckoning following complete loss of primary satellite reception (antenna severance or hardware failure). Verify that the aircraft maintains mission waypoints without wander.
* **Prerequisites & In-Flight Conditions:**
  * Airspeed sensor healthy and pitot tube calibrated ($\pm 1.0\text{ m/s}$).
  * Aircraft in stable cruise in `AUTO` or `GUIDED` mode at 50–100 m AGL.
  * Drag coefficients set: `EK3_DRAG_BCOEF_X = 25`, `EK3_DRAG_BCOEF_Y = 25`.
* **Step 1 — Pre-Test Verification:** Verify groundspeed and airspeed telemetry match expected calm-air values ($V_{\text{tas}} \approx 18\text{ m/s}$).
* **Step 2 — Execution Command (MCDU Line 1L or SITL Console):**
  ```bash
  param set SIM_GPS1_ENABLE 0
  ```
* **Step 3 — Telemetry & Aircraft Flight Response:**
  * MAVLink `GPS_RAW_INT`: $fix\_type$ drops immediately to `0` (NO_FIX), $satellites\_visible$ drops to `0`.
  * EKF3 detects instant satellite loss: horizontal GPS aiding is cleanly decoupled.
  * Aircraft transitions into **Wind-Aided Dead Reckoning**: banks smoothly on flight plan course, holds ground track via pitot airspeed and compass heading. Zero weaving or wing-rocking occurs.
* **Step 4 — Recovery Sequence (Return to Satellite Navigation):**
  ```bash
  param set SIM_GPS1_ENABLE 1
  ```
  *Response:* GPS lock reacquired ($fix\_type = 3$); EKF3 fuses satellites back into navigation state within 3–5 seconds.

---

## SCENARIO 2: Electronic Warfare RF Jamming Countermeasure (Anti-Hunt Protocol)

* **Operational Objective:** Counter hostile broadband RF noise injection. Prevent the aircraft from chasing jumping coordinates (the "here-and-there" hunting phenomenon) by forcing automatic innovation rejection and prompt Dead Reckoning fallback.
* **Technical Root Cause of Wandering:**
  During RF jamming, the receiver does *not* declare $fix\_type = 0$ immediately. It outputs a degraded 3D fix with jumping coordinates. The L1 navigation controller tries to turn toward each false jump, and `AHRS_GPS_USE 1` tilts the horizon with false ground velocities.
* **Step 1 — Execute Anti-Jamming Defensive Pre-Configuration:**
  ```bash
  param set EK3_SRC_OPTIONS 1
  param set FS_EKF_THRESH 0.60
  param set EK3_GLITCH_RAD 15
  param set AHRS_GPS_USE 0
  ```
* **Step 2 — Execution Command (Inject RF Jamming Noise via MCDU Line 2L):**
  ```bash
  param set SIM_GPS1_JAM 1
  ```
* **Step 3 — Telemetry & Aircraft Flight Response:**
  * SITL injects carrier noise: receiver HDOP inflates rapidly ($> 4.5$) and position variance surges.
  * With `FS_EKF_THRESH 0.60`, the EKF failsafe trips within 4–6 seconds.
  * With `EK3_SRC_OPTIONS 1`, EKF3 severs the noisy GPS and cascades into Dead Reckoning.
  * With `AHRS_GPS_USE 0`, the wings remain completely level; erratic weaving is eliminated.
* **Step 4 — Recovery Sequence (Cease Jamming & Restore Navigation):**
  ```bash
  param set SIM_GPS1_JAM 0
  param set AHRS_GPS_USE 1
  ```

---

## SCENARIO 3: Adversarial GPS Spoofing / Innovation Step-Jump Defense

* **Operational Objective:** Validate EKF3 innovation gating defense against hostile terrestrial spoofers attempting to hijack the aircraft trajectory via false pseudoranges or sudden coordinate offset steps.
* **Step 1 — Gating Defensive Pre-Configuration:**
  ```bash
  param set EK3_GLITCH_RAD 15
  param set AHRS_GPS_USE 0
  ```
* **Step 2 — Execution Command (Inject Adversarial Coordinate Step):**
  ```bash
  param set SIM_GPS1_GLT_X 60
  param set SIM_GPS1_GLT_Y 60
  ```
* **Step 3 — Telemetry & Aircraft Flight Response:**
  * The spoofed coordinate jump ($\approx 85\text{ m}$) exceeds the `EK3_GLITCH_RAD` 15 m gate.
  * EKF3 flags `GPS_Glitch: pos step` in MAVLink `STATUSTEXT`; the false position vector is discarded.
  * The aircraft continues holding planned track on internal inertial dead reckoning, completely ignoring the spoofer's pull.
* **Step 4 — Recovery Sequence (Cease Spoofing Signal):**
  ```bash
  param set SIM_GPS1_GLT_X 0
  param set SIM_GPS1_GLT_Y 0
  param set AHRS_GPS_USE 1
  ```

---

## SCENARIO 4: VTOL / Low-Altitude GPS Failure with Optical Flow Fallback

* **Operational Objective:** Ensure stationary hover and station-keeping capability for VTOL platforms or quadplanes when GPS is denied in zero-airspeed hover flight.
* **Step 1 — Sensor Pre-Configuration:**
  ```bash
  param set SIM_FLOW_ENABLE 1
  param set EK3_FLOW_USE 1
  param set EK3_SRC1_VELXY 5
  ```
* **Step 2 — Flight Regime Establishment:** Establish the aircraft in steady hover (`QLOITER` or `QHOVER` mode) at 5–15 m AGL over textured ground.
* **Step 3 — Execution Command (Sever GPS in Hover):**
  ```bash
  param set SIM_GPS1_ENABLE 0
  ```
* **Step 4 — Telemetry & Aircraft Flight Response:**
  * MAVLink `OPTICAL_FLOW` packets stream angular ground pixel displacement rates ($rad/s$).
  * EKF3 seamlessly substitutes satellite horizontal velocity with integrated optical flow ground velocity.
  * Aircraft holds stationary hover coordinates without drift, even with zero forward airspeed over the pitot tube.
* **Step 5 — Recovery Sequence:**
  ```bash
  param set SIM_GPS1_ENABLE 1
  param set EK3_SRC1_VELXY 3
  ```

---

## SCENARIO 5: High-Crosswind Atmospheric Turbulence Dead Reckoning Validation

* **Operational Objective:** Validate EKF3's wind triangle estimation ($\vec{V}_{\text{ground}} = \vec{V}_{\text{tas}} + \vec{W}_{\text{wind}}$) and crab-angle compensation under strong crosswind gusts and Dryden turbulence during GPS-denied navigation.
* **Step 1 — Inject Meteorological Crosswind Environment:**
  ```bash
  param set SIM_WIND_SPD 12.0
  param set SIM_WIND_DIR 270
  param set SIM_WIND_TURB 0.25
  ```
* **Step 2 — Execution Command (Sever GPS under Crosswind):**
  ```bash
  param set SIM_GPS1_ENABLE 0
  ```
* **Step 3 — Telemetry & Aircraft Flight Response:**
  * EKF3 estimates the 12 m/s westerly wind vector from frontal drag deceleration and sideslip drag dynamics.
  * Navigation controller automatically establishes crab angle: $\beta = \arcsin\left(\frac{W_\perp}{V_{\text{tas}}}\right) \approx 35^\circ$ to $40^\circ$.
  * Ground track remains aligned with planned waypoint course line despite turbulent atmospheric buffet.
* **Step 4 — Recovery Sequence:**
  ```bash
  param set SIM_GPS1_ENABLE 1
  param set SIM_WIND_SPD 0
  param set SIM_WIND_TURB 0
  ```

---

# PART III: Master Flight Test Matrix & Telemetry Checksheet

| Scenario | Pre-Requisite Setup | Execution Trigger | Key Telemetry Sign | Evaluation Criteria |
| :--- | :--- | :--- | :--- | :--- |
| **1. Clean GPS Loss** | Airspeed calibrated, `BCOEF_X/Y = 25` | `param set SIM_GPS1_ENABLE 0` | `GPS.fix = 0`<br>`GPS.sats = 0` | Smooth transition to Dead Reckoning; zero wandering or wing-rock. |
| **2. RF Jamming Counter** | `EK3_SRC_OPTIONS 1`<br>`FS_EKF_THRESH 0.60`<br>`AHRS_GPS_USE 0` | `param set SIM_GPS1_JAM 1` | `HDOP > 4.5`<br>`FS_EKF` triggered within 6 s | EKF failsafe trips promptly; drops degraded GPS; zero coordinate hunting. |
| **3. Spoofing Defense** | `EK3_GLITCH_RAD 15`<br>`AHRS_GPS_USE 0` | `param set SIM_GPS1_GLT_X 60` | `GPS_Glitch` in STATUSTEXT | Measurement rejected at gate; internal dead reckoning maintained. |
| **4. Optical Flow Hover** | `SIM_FLOW_ENABLE 1`<br>`EK3_SRC1_VELXY 5` | `param set SIM_GPS1_ENABLE 0` (in hover) | `OPTICAL_FLOW` packet rate $> 20\text{ Hz}$ | Zero positional drift in low-altitude hover; velocity aided by camera. |
| **5. High-Wind DR** | `SIM_WIND_SPD 12`<br>`SIM_WIND_DIR 270` | `param set SIM_GPS1_ENABLE 0` | Crab angle established; ground track true | Correct crosswind crab computed from drag model; path held in turbulence. |

---

### Cockpit MCDU Quick-Key Map Reference
* **Line 1L (`< SIM GPS OFF`):** Stages `param set SIM_GPS1_ENABLE 0` for instant clean dead reckoning test.
* **Line 2L (`< RF JAM 100%`):** Stages `param set SIM_GPS1_JAM 1` for electronic warfare noise testing.
* **Line 3L (`< LAT/LON SPOOF`):** Stages coordinate step glitch to test innovation gating.
* **Line 4L (`< WIND DR ON`):** Stages `EK3_DRAG_BCOEF_X 25` and `EK3_DRAG_BCOEF_Y 25`.
* **Line 5L (`< ANTI-JAM CONFIG`):** Stages `EK3_SRC_OPTIONS 1`, `FS_EKF_THRESH 0.60`, and `AHRS_GPS_USE 0` to eliminate hunting.
* **Line 6R (`< RECOVER ALL`):** Instantly restores all parameters to nominal GPS-guided flight.
