# ATIS BROADCAST INFORMATION BRAVO // AVIONICS PARAMETER EXECUTION MANUAL
**Station:** `VAPO SITL`  
**Purpose:** GNSS Denial, Electronic Jamming, Spoofing Gating & Dead Reckoning Execution  
**Applicability:** ArduPilot EKF3 Navigation Core // Sharkee VTOL Fleet  
**Instruction:** Execute parameters via Cockpit MCDU Line Select Keys or SITL Console  

---

```
================================================================================
ATIS BROADCAST INFORMATION BRAVO // AVIONICS PARAMETER EXECUTION DIRECTIVE
STATION: VAPO SITL | PURPOSE: GNSS DENIAL, JAMMING, SPOOFING & DEAD RECKONING
INSTRUCTION: EXECUTE PARAMETERS VIA COCKPIT MCDU OR SITL MAVLINK CONSOLE
================================================================================
```

---

## 1. GNSS Denial, Hardware Cutoff & Jamming Simulation

### `SIM_GPS1_ENABLE`
- **Type:** SITL Hardware Toggle
- **Default:** `1` (Active) $\rightarrow$ **Execution Target:** `0` (Severed / Denied)
- **MCDU / Console Command:**  
  ```
  param set SIM_GPS1_ENABLE 0
  ```
- **Description:**  
  Simulates complete power cutoff or physical antenna severance to the primary GNSS receiver. When set to `0`, SITL instantly halts satellite tracking, dropping MAVLink `GPS_RAW_INT` to $fix\_type = 0$ (No GPS) and $satellites\_visible = 0$. This forces the ArduPilot EKF3 core to declare horizontal position invalid and transition immediately into inertial Dead Reckoning mode.

---

### `SIM_GPS1_JAM`
- **Type:** SITL Jamming Injection
- **Default:** `0` (Normal RF) $\rightarrow$ **Execution Target:** `1` (RF Jammed)
- **MCDU / Console Command:**  
  ```
  param set SIM_GPS1_JAM 1
  ```
- **Description:**  
  Injects broadband RF interference and noise across GPS L1/L2 carrier frequencies. Simulates terrestrial electronic warfare jammers. When set to `1`, receiver Carrier-to-Noise density ($C/N_0$) drops below the tracking threshold ($< 28\text{ dB-Hz}$), causing carrier phase lock loss, satellite drops, and severe HDOP inflation ($> 5.0$) before fix loss.

---

## 2. GNSS Spoofing Defense, Innovation Gating & Attitude Protection

### `EK3_GLITCH_RAD`
- **Type:** EKF3 Innovation Gate Threshold
- **Default:** `25.0` m $\rightarrow$ **Recommended Combat Setting:** `15.0` to `25.0` m
- **MCDU / Console Command:**  
  ```
  param set EK3_GLITCH_RAD 25
  ```
- **Description:**  
  Defines the maximum horizontal step distance (in meters) allowed between consecutive GPS updates before EKF3 rejects the measurement as a position jump anomaly (glitch or adversarial spoofing attempt). If a spoofed signal attempts to shift the aircraft trajectory faster than natural aerodynamic acceleration limits, EKF3 discards the vector and flags `GPS_Glitch`.

---

### `FS_EKF_THRESH`
- **Type:** Flight Safety Failsafe Ratio
- **Default:** `0.80` $\rightarrow$ **Recommended Setting:** `0.65` to `0.80`
- **MCDU / Console Command:**  
  ```
  param set FS_EKF_THRESH 0.8
  ```
- **Description:**  
  Normalized innovation variance threshold that triggers the autonomous EKF Failsafe. When sensor measurements consistently conflict with the internal inertial prediction (such as during meaconing or creeping spoofing attacks), exceeding this threshold triggers emergency automated actions (contingency loiter, Dead Reckoning Return-to-Launch, or Land).

---

### `AHRS_GPS_USE`
- **Type:** Attitude Filter Sensor Isolation
- **Default:** `1` (GPS Enabled) $\rightarrow$ **Execution Target:** `0` (Isolate AHRS from GPS)
- **MCDU / Console Command:**  
  ```
  param set AHRS_GPS_USE 0
  ```
- **Description:**  
  Controls whether the primary attitude determination filter uses GPS ground velocity to apply centrifugal compensation during coordinated turns ($a_{\text{cent}} = \omega_z \cdot V_{\text{gps}}$). When GPS spoofing or erratic velocity jumps occur, setting this parameter to `0` isolates the artificial horizon, preventing erroneous roll/pitch tilt induced by false satellite velocity.

---

## 3. Dead Reckoning, True Airspeed & Aerodynamic Wind Estimation

### `EK3_DRAG_BCOEF_X`
- **Type:** Aerodynamic Drag Ballistic Coefficient ($kg/m^2$)
- **Default:** `0.0` (Disabled) $\rightarrow$ **Recommended Airframe Setting:** `25.0` to `35.0`
- **MCDU / Console Command:**  
  ```
  param set EK3_DRAG_BCOEF_X 25
  ```
- **Description:**  
  Sets the aircraft's longitudinal frontal ballistic drag coefficient for EKF3's wind estimation filter. In GPS-denied forward flight, EKF3 uses this coefficient along with pitot true airspeed ($V_{\text{tas}}$) and accelerometer deceleration to estimate the horizontal wind vector ($\vec{W}_{\text{wind}}$). This bounds inertial dead reckoning drift indefinitely by synthesizing ground velocity: $\vec{V}_{\text{ground}} = \vec{V}_{\text{air}} + \vec{W}_{\text{wind}}$.

---

### `EK3_DRAG_BCOEF_Y`
- **Type:** Lateral Aerodynamic Drag Coefficient ($kg/m^2$)
- **Default:** `0.0` (Disabled) $\rightarrow$ **Recommended Setting:** `20.0` to `30.0`
- **MCDU / Console Command:**  
  ```
  param set EK3_DRAG_BCOEF_Y 25
  ```
- **Description:**  
  Models lateral fuselage side-force slip dynamics. Enables EKF3 to compute crosswind velocity and crab angle during GPS-denied cruising without requiring dedicated physical side-slip angle vanes.

---

### `EK3_SRC_OPTIONS`
- **Type:** Sensor Fallback Mode Bitmask
- **Default:** `0` (Manual / No Cascade) $\rightarrow$ **Execution Target:** `1` (Automatic Fallback)
- **MCDU / Console Command:**  
  ```
  param set EK3_SRC_OPTIONS 1
  ```
- **Description:**  
  Bitmask parameter that enables automatic internal fallback switching. When Bit 0 is set to `1`, if the primary navigation source (GPS) fails innovation checks or drops fix, EKF3 automatically cascades to secondary available sources (such as Optical Flow or Airspeed/Compass Wind Dead Reckoning) without pilot intervention.

---

## 4. Optical Flow Sensor Simulation & Hover Velocity Fusion

### `SIM_FLOW_ENABLE`
- **Type:** SITL Optical Flow Hardware Simulation
- **Default:** `0` (Disabled) $\rightarrow$ **Execution Target:** `1` (Hardware Simulated)
- **MCDU / Console Command:**  
  ```
  param set SIM_FLOW_ENABLE 1
  ```
- **Description:**  
  Activates downward-facing optical flow camera hardware simulation (e.g., HereFlow, CX-OF). Emits continuous ground pixel motion displacement rates over MAVLink (`OPTICAL_FLOW` packets) based on simulated ground imagery texture.

---

### `EK3_FLOW_USE`
- **Type:** EKF3 Optical Flow Fusion Toggle
- **Default:** `1` (Use Flow) $\rightarrow$ **Contingency Target:** `1` (Enabled)
- **MCDU / Console Command:**  
  ```
  param set EK3_FLOW_USE 1
  ```
- **Description:**  
  Instructs the EKF3 estimation filter to ingest optical flow velocity measurements into the navigation state vector. Essential for stationary hovering, precision landing, and low-altitude VTOL operations where pitot airspeed is near zero.

---

### `EK3_SRC1_VELXY`
- **Type:** Horizontal Velocity Source Selector
- **Default:** `3` (GPS Velocity) $\rightarrow$ **Execution Target:** `5` (Optical Flow)
- **MCDU / Console Command:**  
  ```
  param set EK3_SRC1_VELXY 5
  ```
- **Description:**  
  Selects the sensor used for horizontal velocity aiding ($V_x, V_y$). Setting this parameter to `5` directs EKF3 to use Optical Flow as the primary horizontal velocity reference, completely decoupling velocity estimation from satellite signals.

---

## 5. Environmental Wind & Atmospheric Turbulence Injection

### `SIM_WIND_SPD` / `SIM_WIND_DIR` / `SIM_WIND_TURB`
- **Type:** SITL Environment
- **Range:** Speed: `0`–`30` m/s | Direction: `0`–`359`° | Turbulence: `0.0`–`1.0`
- **MCDU / Console Commands:**  
  ```
  param set SIM_WIND_SPD 7.0
  param set SIM_WIND_DIR 270
  param set SIM_WIND_TURB 0.20
  ```
- **Description:**  
  Controls SITL atmospheric wind speed, compass direction, and Dryden gust turbulence. Used to evaluate aircraft drift compensation, crab angle computation, and the accuracy of EKF3's wind estimation filter under realistic operational weather conditions.
