# GPS DENIAL & DEAD RECKONING FLIGHT EXECUTION MANUAL
**FLEET:** `ARDUPILOT EKF3 UNIVERSAL [ALL FIXED-WING / VTOL]`  
**PURPOSE:** `GNSS DENIAL, ELECTRONIC JAMMING, SPOOFING GATING & DEAD RECKONING PROTOCOLS`  
**INSTRUCTION:** `EXECUTE PARAMETERS VIA COCKPIT MCDU OR SITL CONSOLE`  

---

```
+------------------------------------------------------------------------+
| GPS DENIAL, ELECTRONIC JAMMING & DEAD RECKONING EXECUTION DIRECTIVE   |
| FLEET: ARDUPILOT EKF3 UNIVERSAL             AVIONICS OPERATIONAL SOP   |
+------------------------------------------------------------------------+
```

---

# PART I: AVIONICS PARAMETER TECHNICAL REFERENCE

## 1. GNSS HARDWARE CUTOFF & RF JAMMING SIMULATION

### `SIM_GPS1_ENABLE` [HARDWARE TOGGLE]
- **DEFAULT:** `1` (ACTIVE) $\rightarrow$ **TARGET:** `0` (SEVERED / DENIED)
- **LSK 1L COMMAND:**  
  ```bash
  param set SIM_GPS1_ENABLE 0
  ```
- **DESCRIPTION:**  
  Simulates physical antenna severance or receiver power cutoff. SITL instantly sets `fix_type = 0` (NO_FIX) and `satellites_visible = 0`. EKF3 immediately declares satellite aiding invalid and transitions directly to smooth Dead Reckoning without coordinate jitter.

---

### `SIM_GPS1_JAM` [ELECTRONIC WARFARE INJECTION]
- **DEFAULT:** `0` (NORMAL RF) $\rightarrow$ **TARGET:** `1` (RF JAMMED)
- **LSK 2L COMMAND:**  
  ```bash
  param set SIM_GPS1_JAM 1
  ```
- **DESCRIPTION:**  
  Injects broadband RF interference on GPS L1/L2 carrier frequencies ($C/N_0 < 28\text{ dB-Hz}$), inflating pseudorange noise.  
  **CAUTION:** SITL maintains a degraded 3D fix with jumping coordinates; requires automated gating configuration (Section 2) to eliminate aircraft wandering.

---

## 2. INNOVATION GATING & ATTITUDE HORIZON PROTECTION

### `EK3_GLITCH_RAD` [INNOVATION STEP GATE THRESHOLD]
- **DEFAULT:** `25.0` m $\rightarrow$ **RECOMMENDED:** `15.0` to `20.0` m
- **MCDU COMMAND:**  
  ```bash
  param set EK3_GLITCH_RAD 15
  ```
- **DESCRIPTION:**  
  Defines maximum allowable horizontal step jump between consecutive GPS updates before EKF3 rejects the measurement as anomalous. Rejects abrupt adversarial spoofing coordinates and extreme jamming spikes.

---

### `AHRS_OPTIONS` [DCM FALLBACK INHIBIT BITMASK]
- **DEFAULT:** `0` (FALLBACK ALLOWED) $\rightarrow$ **ANTI-JAM TARGET:** `3` (DCM LOCKOUT)
- **MCDU COMMAND:**  
  ```bash
  param set AHRS_OPTIONS 3
  ```
- **DESCRIPTION:**  
  Critical anti-hunting parameter. Disables automatic fallback from EKF3 to legacy DCM (`Bit 0: FW`, `Bit 1: VTOL`). Under RF jamming, SITL still outputs `status >= 3D`. Without this parameter, `AP_AHRS` bypasses EKF dead reckoning and feeds raw jumping GPS directly to navigation, commanding erratic banks left and right.

---

### `AHRS_GPS_USE` [ATTITUDE FILTER ISOLATION]
- **DEFAULT:** `1` (ENABLED) $\rightarrow$ **HOSTILE RF TARGET:** `0` (ISOLATE AHRS)
- **MCDU COMMAND:**  
  ```bash
  param set AHRS_GPS_USE 0
  ```
- **DESCRIPTION:**  
  Disconnects GPS ground velocity from attitude centrifugal turn compensation ($a_{\text{cent}} = \omega_z \cdot V_{\text{gps}}$). Prevents erratic GPS velocity spikes from corrupting the artificial horizon and inducing violent wing-rocking.

---

## 3. DEAD RECKONING & AERODYNAMIC WIND ESTIMATION

### `EK3_DRAG_BCOEF_X` & `EK3_DRAG_BCOEF_Y` [DRAG BALLISTICS]
- **DEFAULT:** `0.0` (DISABLED) $\rightarrow$ **AIRFRAME TARGET:** `25.0` to `35.0` ($kg/m^2$)
- **LSK 5R COMMANDS:**  
  ```bash
  param set EK3_DRAG_BCOEF_X 25
  param set EK3_DRAG_BCOEF_Y 25
  ```
- **DESCRIPTION:**  
  Calibrates longitudinal and lateral airframe ballistic drag. In GPS-denied flight, EKF3 combines pitot true airspeed ($V_{\text{tas}}$) with accelerometer drag deceleration to estimate horizontal wind ($\vec{W}$), synthesizing ground track: $\vec{V}_{\text{ground}} = \vec{V}_{\text{air}} + \vec{W}$.

---

### `EK3_OPTIONS` [JAMMING EXPECTED EKF BEHAVIOR]
- **DEFAULT:** `0` (STANDARD EKF) $\rightarrow$ **ANTI-JAM TARGET:** `1` (JAMMING EXPECTED)
- **LSK 4L COMMAND:**  
  ```bash
  param set EK3_OPTIONS 1
  ```
- **DESCRIPTION:**  
  Bit 0 (`JammingExpected`). In EKF3, prevents automatic position reset to degraded GPS upon timeout. Sets `waitingForGpsChecks = true` and `gpsDataToFuse = false`, isolating the filter in pure Dead Reckoning until all pre-flight quality checks pass continuously.

---

## 4. OPTICAL FLOW SIMULATION & HOVER VELOCITY FUSION

### `SIM_FLOW_ENABLE` / `EK3_FLOW_USE` / `EK3_SRC1_VELXY` [FLOW FUSION]
- **DEFAULT:** `0` / `1` / `3` $\rightarrow$ **EXECUTION TARGET:** `1` / `1` / `5`
- **MCDU COMMANDS:**  
  ```bash
  param set SIM_FLOW_ENABLE 1
  param set EK3_SRC1_VELXY 5
  ```
- **DESCRIPTION:**  
  Activates simulated downward optical flow camera and directs EKF3 to ingest pixel displacement rates as primary horizontal velocity ($V_x, V_y$), decoupling hover navigation from satellites.

---

## 5. ENVIRONMENTAL WIND & DRYDEN TURBULENCE INJECTION

### `SIM_WIND_SPD` / `SIM_WIND_DIR` / `SIM_WIND_TURB` [METEOROLOGY]
- **RANGE:** SPD: `0`–`30` m/s | DIR: `0`–`359`° | TURB: `0.0`–`1.0`
- **MCDU COMMANDS:**  
  ```bash
  param set SIM_WIND_SPD 12.0
  param set SIM_WIND_DIR 270
  param set SIM_WIND_TURB 0.25
  ```

---

# PART II: TACTICAL FLIGHT SCENARIO EXECUTION PROTOCOLS

---

## SCENARIO 1: TOTAL GNSS HARDWARE CUTOFF [CLEAN DEAD RECKONING]

* **OBJECTIVE:** Evaluate pure aerodynamic and inertial dead reckoning following complete loss of primary satellite reception (antenna severance or hardware failure). Verify aircraft tracks waypoints without wander.
* **PREREQUISITES:** Airspeed calibrated ($\pm 1.0\text{ m/s}$); cruise in `AUTO` or `GUIDED` at 50–100 m AGL; drag coefficients set: `EK3_DRAG_BCOEF_X/Y = 25`.
* **LSK 1L TRIGGER COMMAND:**
  ```bash
  param set SIM_GPS1_ENABLE 0
  ```
* **TELEMETRY DYNAMICS & FLIGHT RESPONSE:**
  * MAVLink `GPS_RAW_INT`: $fix\_type$ drops immediately to `0` (NO_FIX), $satellites\_visible = 0$.
  * EKF3 detects instant satellite loss; cleanly decouples horizontal GPS fusion.
  * Aircraft enters **Wind Dead Reckoning**: smoothly banks along waypoint legs, holds track via airspeed and compass heading. Zero weaving or wing-rocking occurs.
* **RECOVERY COMMAND:**
  ```bash
  param set SIM_GPS1_ENABLE 1
  ```
  *Response:* GPS lock reacquired ($fix\_type = 3$); fused in 3–5 seconds.

---

## SCENARIO 2: EW RF JAMMING COUNTERMEASURE [ANTI-HUNT PROTOCOL]

* **OBJECTIVE:** Counter broadband RF jamming. Prevent aircraft from chasing jumping coordinates (the "here-and-there" hunting phenomenon) by eliminating legacy DCM fallback and locking EKF3 in aerodynamic Dead Reckoning.
* **ROOT CAUSE OF WANDERING (FROM SOURCE CODE):**
  1. **Automatic DCM Fallback (`AP_AHRS.cpp:1813`):** Default `AHRS_OPTIONS = 0` causes `AP_AHRS` to drop into DCM whenever EKF stops using GPS while the GPS receiver reports `status >= 3D`. DCM has **no dead reckoning filter**; it feeds raw jumping coordinates (up to 400 m/s noise) straight to navigation!
  2. **EKF Timeout Reset (`AP_NavEKF3_PosVelFusion.cpp:945`):** Without `EK3_OPTIONS = 1`, when `posTimeout` expires after 5–10 seconds of rejected GPS data, EKF3 automatically calls `ResetPosition()` directly to the bad GPS.
  3. **Wind Estimation Convergence (`arduplane.py:2025`):** Dead reckoning calculates ground velocity via $\vec{V}_{\text{ground}} = \vec{V}_{\text{tas}} + \vec{W}_{\text{wind}}$. If jamming is injected before EKF learns the wind vector, the aircraft will wander.
* **STEP 1 — EXECUTE ANTI-JAM PRE-CONFIGURATION (LSK 4L, 4R, 5L, 5R):**
  ```bash
  param set AHRS_OPTIONS 3
  param set EK3_OPTIONS 1
  param set AHRS_GPS_USE 0
  param set EK3_DRAG_BCOEF_X 25
  param set EK3_DRAG_BCOEF_Y 25
  ```
* **STEP 2 — MANDATORY WIND-LEARNING ORBIT (PRIOR TO JAMMING):**
  * Climb to cruise altitude and fly in `AUTO` or `LOITER` turns for **20 seconds** with good GPS to allow EKF3 to converge horizontal wind states ($\vec{W}$).
* **STEP 3 — INJECT RF JAMMING NOISE (LSK 2L TRIGGER):**
  ```bash
  param set SIM_GPS1_JAM 1
  ```
* **TELEMETRY DYNAMICS & FLIGHT RESPONSE:**
  * SITL injects noise; EKF3 detects innovation errors and isolates GPS inputs.
  * With `AHRS_OPTIONS 3`, DCM lockout blocks bypass; aircraft remains strictly in EKF3.
  * With `EK3_OPTIONS 1`, EKF3 holds Dead Reckoning without resetting position to noise.
  * Aircraft flies straight on planned track with zero wandering or wing-rocking.
* **RECOVERY SEQUENCE:**
  ```bash
  param set SIM_GPS1_JAM 0
  param set AHRS_GPS_USE 1
  ```

---

## SCENARIO 3: ADVERSARIAL GPS SPOOFING STEP-JUMP DEFENSE

* **OBJECTIVE:** Validate EKF3 innovation gating defense against hostile terrestrial spoofers attempting to hijack the aircraft trajectory via false pseudoranges or sudden coordinate offset steps.
* **STEP 1 — GATING DEFENSIVE PRE-CONFIGURATION:**
  ```bash
  param set EK3_GLITCH_RAD 15
  param set AHRS_GPS_USE 0
  ```
* **STEP 2 — INJECT COORDINATE STEP OFFSET (LSK 3L TRIGGER):**
  ```bash
  param set SIM_GPS1_GLT_X 60
  param set SIM_GPS1_GLT_Y 60
  ```
* **TELEMETRY DYNAMICS & FLIGHT RESPONSE:**
  * Spoofed coordinate jump ($\approx 85\text{ m}$) exceeds the `EK3_GLITCH_RAD` 15 m gate.
  * EKF3 flags `GPS_Glitch: pos step` in MAVLink `STATUSTEXT`; false vector is rejected.
  * Aircraft continues holding planned track on internal dead reckoning, completely ignoring the spoofer's pull.
* **RECOVERY COMMANDS:**
  ```bash
  param set SIM_GPS1_GLT_X 0
  param set SIM_GPS1_GLT_Y 0
  param set AHRS_GPS_USE 1
  ```

---

## SCENARIO 4: VTOL / LOW-ALTITUDE HOVER OPTICAL FLOW FALLBACK

* **OBJECTIVE:** Ensure stationary hover and station-keeping capability for VTOL platforms or quadplanes when GPS is denied in zero-airspeed hover flight.
* **STEP 1 — SENSOR PRE-CONFIGURATION:**
  ```bash
  param set SIM_FLOW_ENABLE 1
  param set EK3_FLOW_USE 1
  param set EK3_SRC1_VELXY 5
  ```
* **STEP 2 — FLIGHT REGIME ESTABLISHMENT:**
  Establish aircraft in steady hover (`QLOITER` or `QHOVER` mode) at 5–15 m AGL over textured ground.
* **STEP 3 — SEVER GPS IN HOVER (LSK 1L TRIGGER):**
  ```bash
  param set SIM_GPS1_ENABLE 0
  ```
* **TELEMETRY DYNAMICS & FLIGHT RESPONSE:**
  * MAVLink `OPTICAL_FLOW` packets stream angular ground pixel displacement rates ($rad/s$).
  * EKF3 seamlessly substitutes satellite horizontal velocity with integrated optical flow ground velocity.
  * Aircraft holds stationary hover coordinates without drift, even with zero forward airspeed over the pitot tube.
* **RECOVERY COMMANDS:**
  ```bash
  param set SIM_GPS1_ENABLE 1
  param set EK3_SRC1_VELXY 3
  ```

---

## SCENARIO 5: HIGH-CROSSWIND TURBULENCE DEAD RECKONING

* **OBJECTIVE:** Validate EKF3 wind triangle estimation ($\vec{V}_{\text{ground}} = \vec{V}_{\text{tas}} + \vec{W}_{\text{wind}}$) and crab-angle compensation under strong crosswind gusts and Dryden turbulence during GPS denial.
* **STEP 1 — INJECT CROSSWIND METEOROLOGY:**
  ```bash
  param set SIM_WIND_SPD 12.0
  param set SIM_WIND_DIR 270
  param set SIM_WIND_TURB 0.25
  ```
* **STEP 2 — SEVER GPS UNDER CROSSWIND:**
  ```bash
  param set SIM_GPS1_ENABLE 0
  ```
  *Response:* Aircraft computes crab angle ($\beta \approx 35^\circ$), holding ground track true.
* **RECOVERY:**
  ```bash
  param set SIM_GPS1_ENABLE 1
  param set SIM_WIND_SPD 0
  ```

---

# PART III: MASTER FLIGHT TEST MATRIX

| SCENARIO | PRE-SETUP | TRIGGER | KEY TELEMETRY | EVALUATION |
| :--- | :--- | :--- | :--- | :--- |
| **1. CLEAN LOSS** | Airspeed valid, `BCOEF = 25` | `param set SIM_GPS1_ENABLE 0` | `GPS.fix = 0`<br>`GPS.sats = 0` | Smooth transition to Dead Reckoning; zero wandering or wing-rock. |
| **2. JAM COUNTER** | `AHRS_OPT 3`<br>`EK3_OPT 1`<br>`AHRS_GPS 0`<br>`20s Wind Orbit` | `param set SIM_GPS1_JAM 1` | `DCM lockout`<br>`waitingChecks 1`<br>`DR active` | DCM lockout active; EKF holds Dead Reckoning without coordinate reset; zero wandering. |
| **3. SPOOF DEFENSE** | `GLITCH_RAD 15`<br>`AHRS_GPS 0` | `param set SIM_GPS1_GLT_X 60` | `GPS_Glitch` in STATUSTEXT | Measurement rejected at gate; internal dead reckoning maintained. |
| **4. FLOW HOVER** | `FLOW_ENABLE 1`<br>`SRC1_VELXY 5` | `param set SIM_GPS1_ENABLE 0` | `OPTICAL_FLOW` rate $> 20\text{ Hz}$ | Zero positional drift in low-altitude hover; velocity aided by camera. |
| **5. HIGH-WIND DR** | `WIND_SPD 12`<br>`WIND_DIR 270` | `param set SIM_GPS1_ENABLE 0` | Crab angle established; track true | Correct crosswind crab computed from drag model; path held in gusts. |

---

### COCKPIT MCDU / LSK QUICK-KEY MAP REFERENCE:
* **< LSK 1L:** Clean GPS Cutoff (`SIM_GPS1_ENABLE 0`) $\quad\leftrightarrow\quad$ **LSK 1R >:** RECOVER GPS (`ENABLE 1`)
* **< LSK 2L:** RF Jamming Noise (`SIM_GPS1_JAM 1`) $\quad\leftrightarrow\quad$ **LSK 2R >:** CLEAR JAMMING (`JAM 0`)
* **< LSK 3L:** Spoofing Offset (`SIM_GPS1_GLT_X/Y`) $\quad\leftrightarrow\quad$ **LSK 3R >:** RESET GLITCH OFFSETS
* **< LSK 4L:** Jamming Expect (`EK3_OPTIONS 1`) $\quad\leftrightarrow\quad$ **LSK 4R >:** DCM Lockout (`AHRS_OPTIONS 3`)
* **< LSK 5L:** Isolate AHRS (`AHRS_GPS_USE 0`) $\quad\leftrightarrow\quad$ **LSK 5R >:** Drag Coeff (`BCOEF_X 25`)
* **< LSK 6L:** OPEN THIS SOP MANUAL $\quad\leftrightarrow\quad$ **LSK 6R >:** RETURN TO NAV POS
