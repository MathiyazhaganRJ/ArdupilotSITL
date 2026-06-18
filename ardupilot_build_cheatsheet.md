# ArduPilot Build Cheat Sheet (WSL/Ubuntu)

This is a comprehensive, quick-reference guide for building ArduPilot firmware, running SITL simulations, and helpful WAF commands.

## 1. Initial Setup (One-time only)
These commands set up your ArduPilot environment on a fresh WSL/Ubuntu installation.

```bash
# Navigate to your Linux home directory
cd ~

# Clone the repository
git clone https://github.com/ArduPilot/ardupilot.git
cd ardupilot

# Initialize submodules (downloads required libraries)
git submodule update --init --recursive

# Install prerequisite tools and compilers
Tools/environment_install/install-prereqs-ubuntu.sh -y

# Reload your terminal profile to apply paths
. ~/.profile
```

---

## 2. Verify Compiler Installation
To ensure the ARM compiler was successfully installed and added to your path, run this check:

```bash
arm-none-eabi-gcc --version
```
*If this prints a version number, you are good to go! If it says "command not found", try running `. ~/.profile` again or restart your terminal.*

---

## 3. Getting the Latest Code (Before building)
If you haven't built in a while, fetch the latest updates from the ArduPilot servers.

```bash
cd ~/ardupilot
git pull
git submodule update --init --recursive
```

---

## 4. Configuring and Compiling for Hardware
Before you compile for a physical flight controller, you must configure `waf` for that specific board.

```bash
cd ~/ardupilot

# --- 1. CONFIGURATION COMMANDS ---
# Configure for your specific board (Example: Matek F405-TE)
./waf configure --board MatekF405-TE

# Configure for Cube Orange
./waf configure --board CubeOrange

# List all supported boards (if you don't know the exact name)
./waf list_boards

# --- 2. COMPILE COMMANDS ---
# Compile the firmware for your vehicle type
./waf plane     # For Fixed Wing (Planes)
./waf copter    # For Multirotors (Quads, Hexas, etc.)
./waf heli      # For Traditional Helicopters
./waf rover     # For Rovers and Boats
./waf sub       # For Submarines

# --- 3. UPLOAD COMMANDS ---
# If your flight controller is plugged in via USB and mapped to WSL, 
# you can compile and upload in one command:
./waf plane --upload
```

### Where is the compiled firmware?
Once finished, the compiled files are located at:
`~/ardupilot/build/<board_name>/bin/`

Look for the `.apj` file (e.g. `arduplane.apj`) and flash it to your flight controller using Mission Planner if you didn't use the `--upload` flag.

---

## 5. Custom Firmware (Enabling/Disabling Features)
Flight controllers with a 1MB flash limit (like the Matek F405) disable non-essential features to save space. You can manually enable them using `waf configure` flags. 

*(Note: Flags are strictly case-sensitive!)*

```bash
cd ~/ardupilot

# Example: Enable System ID mode, Enable ESC Telemetry, and disable QuadPlane to save space
./waf configure --board MatekF405-TE --enable-PLANE_SYSTEMID --enable-RPM_ESC_TELEM --disable-QUADPLANE

# View EVERY available enable/disable flag you can use
./waf configure --help
```

---

## 6. JSBSim Installation (For Advanced SITL)
ArduPilot has a basic simulator, but if you want high-fidelity aerodynamics for ArduPlane, you must install JSBSim.

```bash
# 1. Clone and build JSBSim in your home directory
cd ~
git clone https://github.com/JSBSim-Team/jsbsim.git
cd jsbsim
mkdir build
cd build
cmake ..
make -j4

# 2. Add JSBSim to your terminal path
nano ~/.profile
# Paste this at the very bottom: export PATH=$PATH:$HOME/jsbsim/build/src
# Save (Ctrl+O, Enter) and Exit (Ctrl+X)

# 3. Reload your terminal profile
. ~/.profile
```

---

## 7. Running SITL (`sim_vehicle.py`)
When simulating, you do not use `./waf` directly. The `sim_vehicle.py` script configures everything for you and launches the simulator. All commands are run from the `~/ardupilot` root folder.

### Command Flags Breakdown:
*   `-v`: Vehicle type (e.g., `ArduPlane`, `ArduCopter`).
*   `-f`: Simulator backend (e.g., `jsbsim:Rascal`). If omitted, uses ArduPilot's default internal physics.
*   `-w`: **Wipe EEPROM**. Deletes all saved parameters and factory-resets the flight controller. Use this the very first time you test a new model, or to fix corrupted parameters. **Omit this flag** for normal flights if you want to keep your saved settings (like PIDs, LiDAR settings, or Waypoints).
*   `--console`: Opens the MAVProxy terminal.
*   `--map`: Opens the MAVProxy map window.

```bash
cd ~/ardupilot

# --- STANDARD SITL COMMANDS (Basic Physics) ---
# Simulating a Quadcopter (ArduCopter)
Tools/autotest/sim_vehicle.py -v ArduCopter --console --map

# Simulating a Fixed Wing Plane (ArduPlane)
Tools/autotest/sim_vehicle.py -v ArduPlane --console --map

# --- JSBSIM SITL COMMANDS (High-Fidelity Physics) ---
# Requires JSBSim installed (See Section 6). 
# The 'Rascal' is a default plane model provided by ArduPilot
Tools/autotest/sim_vehicle.py -v ArduPlane -f jsbsim:Rascal --console --map
```

> [!WARNING]
> **Switching Back to Hardware!**
> Running `sim_vehicle.py` automatically reconfigures your build environment for a PC simulation. If you want to compile firmware for your Matek board again, you **MUST** run `./waf configure --board MatekF405-TE` before running `./waf plane`.

---

## 8. Pro Tips & Advanced Tricks!
Here are some extremely useful tricks that many beginners miss, but will save you hours of headaches:

```bash
# --- 1. WIPE SIMULATOR MEMORY ---
# If your SITL simulation starts acting crazy or crashing, it's usually 
# because of corrupted parameters from a previous flight. 
# Add the '-w' flag to wipe the EEPROM and start fresh!
Tools/autotest/sim_vehicle.py -v ArduPlane -w --console --map

# --- 2. START SIMULATOR AT A CUSTOM LOCATION ---
# Bored of the default Australian test field? Add '-L' to spawn anywhere.
# (e.g., KSFO is San Francisco Airport)
Tools/autotest/sim_vehicle.py -v ArduPlane -L KSFO --console --map

# --- 3. UPLOAD TO A SPECIFIC PORT ---
# If '--upload' fails because it can't find your flight controller, 
# you can manually specify the COM/Serial port.
./waf plane --upload --port /dev/ttyACM0

# --- 4. EXTREME DEBUGGING ---
# If your firmware is randomly rebooting the flight controller, build it 
# with the debug flag so you can use GDB to track down the crash.
./waf configure --board MatekF405-TE --debug
```

---

## 9. Helpful WAF Commands

```bash
# Cleans out the current build files (fast, fixes minor glitches)
./waf clean

# Completely nukes the build directory and configuration (very thorough)
./waf distclean

# Clean and reconfigure (highly recommended if you switch branches!)
./waf distclean
./waf configure --board <board_name>
```
