# FLIGHT CREW OPERATIONAL BULLETIN // ATIS INFORMATION BRAVO
## ARDUPILOT EKF3 DEAD RECKONING, GNSS DENIAL, ELECTRONIC JAMMING & SPOOFING DEFENSE SOP
**Document ID:** `ATIS-ARD-EKF3-SOP-2026-B`  
**Classification:** TACTICAL FLIGHT OPERATIONS BULLETIN / ACADEMIC ENGINEERING REFERENCE  
**Aircraft Type:** Sharkee VTOL / Fixed-Wing UAV Fleet  
**Avionics Architecture:** ArduPilot EKF3 (Extended Kalman Filter 3) Navigation Core  
**Issue Date:** October 2026  

---

```
================================================================================
ATIS BROADCAST INFORMATION BRAVO
SPECIAL OPERATIONAL NOTAM // GNSS CONTINGENCY & DEAD RECKONING PROTOCOLS
VAPO / METAR 281825Z 27010KT CAVOK 26/18 Q1013 NOSIG
WARNING: REGIONAL GNSS UNRELIABILITY REPORTED. SPOOFING AND JAMMING VECTORS
ACTIVE. CREW DIRECTED TO OBSERVE EKF3 DEAD RECKONING STANDARD OPERATING PROCEDURES.
MCDU TWO-STEP STAGED EXECUTION MANDATED FOR ALL AVIONICS RECONFIGURATIONS.
================================================================================
```

---

## 1. Executive Summary & Operational Context

In modern tactical and civilian aviation, autonomous and semi-autonomous unmanned aircraft systems (UAS) face severe vulnerability to Global Navigation Satellite System (GNSS) interruption. These vulnerabilities categorize broadly into:
1. **Total Signal Denial (Space-Vehicle Loss):** Physical shielding, terrain masking, antenna severing, or anti-satellite disruptions resulting in zero carrier lock.
2. **RF Electronic Jamming:** High-power broadband or continuous wave (CW) RF flooding on L1 (1575.42 MHz), L2, or L5 frequencies that drives the receiver's Carrier-to-Noise density ($C/N_0$) below tracking thresholds.
3. **GNSS Spoofing & Meaconing:** Deceptive, synthesized, or delayed RF broadcasting designed to corrupt navigation filters, misguide trajectories, or induce Controlled Flight Into Terrain (CFIT).

ArduPilot’s **EKF3 (Extended Kalman Filter 3)** incorporates a robust 24-state estimation architecture capable of detecting signal anomalies, isolating corrupted sensor vectors, and transitioning autonomously to **Dead Reckoning (DR)** via inertial strapdown integration, aerodynamic wind triangle estimation, and optical flow velocity fusion.

---

## 2. Mathematical Formulations of EKF3 Dead Reckoning & Threat Mitigation

### 2.1 Strapdown Inertial Mechanization Equations

When all external position references are lost, navigation relies on high-rate numerical integration of the tri-axial accelerometer $\mathbf{f}^b$ and tri-axial gyroscope $\boldsymbol{\omega}_{ib}^b$ measurements:

$$\dot{\mathbf{C}}_b^n = \mathbf{C}_b^n \left[ \boldsymbol{\omega}_{ib}^b - \mathbf{b}_g - \boldsymbol{\eta}_g \right]_\times$$

$$\dot{\mathbf{v}}^n = \mathbf{C}_b^n \left( \mathbf{f}^b - \mathbf{b}_a - \boldsymbol{\eta}_a \right) + \mathbf{g}^n$$

$$\dot{\mathbf{p}}^n = \mathbf{v}^n$$

Where:
- $\mathbf{C}_b^n$: Direction cosine transformation matrix from aircraft body frame ($b$) to local navigation frame ($n$, North-East-Down).
- $\mathbf{b}_g, \mathbf{b}_a$: Gyroscope and accelerometer bias vectors.
- $\boldsymbol{\eta}_g, \boldsymbol{\eta}_a$: Measurement Gaussian noise vectors.
- $\mathbf{g}^n$: Local gravitational acceleration vector $\begin{bmatrix} 0 & 0 & g \end{bmatrix}^T$.

### 2.2 Unconstrained Covariance Growth in Pure Inertial DR

Without velocity or position correction, accelerometer bias $\mathbf{b}_a$ produces a position drift error that expands quadratically, while gyro bias $\mathbf{b}_g$ induces an error expanding cubically over time $t$:

$$\delta \mathbf{p}(t) \approx \delta \mathbf{p}_0 + \delta \mathbf{v}_0 t + \frac{1}{2} \mathbf{b}_a t^2 + \frac{1}{6} \left( \mathbf{b}_g \times \mathbf{g}^n \right) t^3$$

In practical UAV operations without aiding sensors, standard tactical-grade MEMS IMUs produce an operational drift radius $\sigma_{pos}(t)$ of approximately:

$$\sigma_{pos}(t) \approx 4.0\text{ m} + 1.2 \cdot t \quad [\text{meters}]$$

*(This dynamic drift is rendered in real-time within the 3D Sharkee Visualizer as an expanding translucent laser beacon and uncertainty ground circle).*

---

### 2.3 Innovation Gating & Spoofing Rejection (Chi-Square Detection)

EKF3 prevents spoofed GNSS positions from corrupting the internal state by subjecting all incoming measurements $\mathbf{z}_k$ to a Mahalanobis distance innovation test before fusion:

The measurement residual (innovation) is:
$$\mathbf{y}_k = \mathbf{z}_k - \mathbf{h}(\hat{\mathbf{x}}_k^-)$$

The innovation covariance matrix $\mathbf{S}_k$ is:
$$\mathbf{S}_k = \mathbf{H}_k \mathbf{P}_k^- \mathbf{H}_k^T + \mathbf{R}_k$$

The normalized innovation squared (Mahalanobis distance) is evaluated against the Chi-Square ($\chi^2$) distribution threshold:
$$d_M^2 = \mathbf{y}_k^T \mathbf{S}_k^{-1} \mathbf{y}_k \le \gamma_{\text{gate}}$$

Where:
- $\mathbf{H}_k$: Observation Jacobian matrix.
- $\mathbf{P}_k^-$: A priori state covariance estimate.
- $\mathbf{R}_k$: Measurement noise covariance matrix.
- $\gamma_{\text{gate}}$: Threshold parameterized by `EK3_GLITCH_RAD` and `FS_EKF_THRESH`.

If $d_M^2 > \gamma_{\text{gate}}$, EKF3 discards the measurement as a **Glitch/Spoofing event**, sets the `gps_glitch` flag to `DETECTED`, prevents Kalman gain computation ($\mathbf{K}_k$), and continues operating on inertial dead reckoning.

---

### 2.4 Aerodynamic Wind Vector & True Airspeed (TAS) Dead Reckoning

For fixed-wing and hybrid VTOL aircraft in cruise, unconstrained inertial drift can be bounded by synthesizing horizontal ground velocity through the aerodynamic wind triangle:

$$\vec{\mathbf{V}}_{\text{ground}} = \mathbf{R}_{b}^{n}(\phi, \theta, \psi) \begin{bmatrix} V_{\text{tas}} \\ 0 \\ 0 \end{bmatrix} + \vec{\mathbf{W}}_{\text{wind}}$$

Where:
- $V_{\text{tas}}$: True Airspeed measured by the pitot-static differential pressure sensor.
- $\mathbf{R}_{b}^{n}(\phi, \theta, \psi)$: Euler transformation from aircraft body frame to NED navigation frame using compass yaw $\psi$.
- $\vec{\mathbf{W}}_{\text{wind}}$: Estimated 2D horizontal wind vector $[W_N, W_E]^T$.

EKF3 estimates the wind states continuously by measuring the aerodynamic drag deceleration along the X and Y axes using body drag ballistic coefficients:

$$\dot{W}_N = \eta_{w_N}, \quad \dot{W}_E = \eta_{w_E}$$
$$a_{\text{drag}, x} = -\frac{1}{2} \rho V_{\text{tas}}^2 \cdot \frac{1}{\text{EK3\_DRAG\_BCOEF\_X}}$$

This enables ArduPilot to maintain stable horizontal velocity and navigation waypoints indefinitely in GPS-denied environments without divergence.

---

### 2.5 Optical Flow Ground Velocity Aiding

For low-altitude loitering, hover, and VTOL terminal approach, a downward optical flow sensor (e.g., HereFlow, CX-OF) measures angular pixel velocity $(\dot{\theta}_x, \dot{\theta}_y)$. Deriving translational ground velocity requires body angular rate compensation from the gyroscopes ($\omega_x, \omega_y$) and ground range ($h$) from an altimeter or LiDAR:

$$v_x = h \left( \dot{\theta}_x - \omega_y \right)$$
$$v_y = h \left( \dot{\theta}_y + \omega_x \right)$$

When `EK3_SRC1_VELXY = 5`, EKF3 fuses these velocities into the state vector, halting horizontal drift completely.

---

## 3. ArduPilot EKF3 Parameter Register Reference

The following table details the primary SITL simulation triggers and EKF3 flight parameters configured via the cockpit MCDU:

| Parameter | Type | Default | Combat / DR Setting | Functional Description |
|:---|:---:|:---:|:---:|:---|
| `SIM_GPS1_ENABLE` | SITL | `1` | `0` | Disables GNSS receiver power in simulation to test open-loop dead reckoning. |
| `SIM_GPS1_JAM` | SITL | `0` | `1` | Injects RF electronic jamming noise, collapsing $C/N_0$ and triggering sat unlock. |
| `SIM_FLOW_ENABLE` | SITL | `0` | `1` | Simulates downward optical flow sensor hardware for hover velocity fusion. |
| `EK3_FLOW_USE` | Core | `1` | `1` | Enables EKF3 optical flow measurement fusion (`1=Enabled`, `0=Disabled`). |
| `EK3_SRC1_VELXY` | Core | `3` (GPS) | `5` (Flow) / `0` | Selects horizontal velocity source (`3=GPS`, `5=Optical Flow`, `0=None`). |
| `EK3_SRC_OPTIONS` | Core | `0` | `1` | Automatic fallback to secondary velocity/position sources upon primary loss. |
| `EK3_DRAG_BCOEF_X` | Core | `0` | `25`–`35` | Ballistic drag coefficient along X-axis ($kg/m^2$) for airspeed wind estimation. |
| `EK3_DRAG_BCOEF_Y` | Core | `0` | `20`–`30` | Ballistic drag coefficient along lateral Y-axis for crosswind side-slip estimation. |
| `EK3_GLITCH_RAD` | Gate | `25.0` | `15.0`–`25.0` | Radius threshold (meters) for rejecting spoofed position anomalies. |
| `FS_EKF_THRESH` | Gate | `0.80` | `0.65`–`0.80` | Normalized EKF innovation variance threshold that triggers dead reckoning failsafe. |
| `AHRS_GPS_USE` | Core | `1` | `0` | Forces AHRS attitude filter to isolate and ignore GPS velocity aiding. |

---

## 4. Standard Operating Procedures (SOP) & Aircrew Checklist

```
+------------------------------------------------------------------------------+
|                     EMERGENCY DRILL: GNSS CONTINGENCY / EKF3-DR              |
+------------------------------------------------------------------------------+
[ ] 1. ANNUNCIATOR SCAN:
       - Verify amber 'DR' annunciator on MCDU / HUD is ILLUMINATED.
       - Check MCDU Line 1L: displays '< NO GPS [DR]'.
       - Check MCDU Line 1R: displays 'DENIED >'.

[ ] 2. SPOOFING / JAMMING ISOLATION:
       - If spoofing suspected (aircraft executing uncommanded course change):
         a. On MCDU PARAMS page, select '5L: < AHRS_GPS [0]'.
         b. Verify scratchpad reads: 'STG: AHRS_GPS_USE 0 > PRESS EXEC'.
         c. Press illuminated green 'EXEC' button to commit isolation.

[ ] 3. ENGAGE AIRSPEED & WIND DEAD RECKONING:
       - Verify pitot heater ON and airspeed indicator healthy.
       - Verify wind vector is displayed on ND compass rose (e.g., 270° / 5.0 m/s).
       - Select MCDU Line 4R: 'EK3_SRC_OPTIONS [1]' -> Press EXEC.

[ ] 4. OPTICAL FLOW ACTIVATION (VTOL / LOW ALTITUDE LOITER):
       - If AGL < 50m and over textured terrain:
         a. MCDU SIM CTL page: Select '3R: < FLOW_USE [1]' -> Press EXEC.
         b. Select '4L: < VEL FLOW [5]' -> Press EXEC.
         c. Observe uncertainty disc radius stabilization.

[ ] 5. NAVIGATION RECOVERY / CONTINGENCY RALLY:
       - Monitor expanding 3D uncertainty sphere (±1.2 m/s elapsed drift).
       - Avoid terrain obstacles using terrain graph (AGL clearance).
       - If GNSS signal clears, stage 'SIM_GPS1_ENABLE 1' or 'SIM_GPS1_JAM 0' -> EXEC.
       - Verify primary fix restores to '< 3D GPS FIX' and 'DR' annunciator extinguishes.
+------------------------------------------------------------------------------+
```

---

## 5. Cockpit MCDU Two-Step Execution Standard

To avoid accidental parameter alteration during high-workload flight phases, all cockpit parameter interactions in the visualizer adhere to the authentic **Boeing FMC / Airbus MCDU Two-Step Staged Execution Workflow**:

1. **Selection & Staging (Line Select Keys 1L–6L / 1R–6R):**
   - Pressing a side key or an ATIS simulation trigger stages the command into the CRT scratchpad:  
     `[ STG: PARAM_NAME VALUE > PRESS EXEC ]`
   - The cyan `MSG` annunciator illuminates.
   - The green `EXEC` LED bar illuminates, pulsing in an armed state.
2. **Commitment & Execution (EXEC Key):**
   - The pilot confirms the parameter on the display and presses the physical `EXEC` key.
   - The parameter is transmitted over MAVLink WebSocket directly to ArduPilot SITL.
   - Scratchpad flashes `[ EXEC: PARAM_NAME = VALUE OK ]` for 2.5 seconds before clearing to `[ READY ]`.
3. **Cancellation (CLR Key):**
   - Pressing `CLR` immediately flushes the staged parameter and scratchpad without modifying the aircraft's state.

---

*Authored and Approved for Sharkee Flight Operations & SITL Tactical Evaluation.*  
*Distributed via ATIS Broadcast System Bravo.*
