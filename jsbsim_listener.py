import socket

UDP_IP = "127.0.0.1"
UDP_PORT = 8999

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))

print(f"Listening for JSBSim live telemetry on UDP {UDP_PORT}...")
print("Format: Lift(lbs), Drag(lbs), Alpha(deg), Beta(deg), Airspeed(kts)")
print("-" * 60)

try:
    while True:
        data, addr = sock.recvfrom(1024) # buffer size is 1024 bytes
        # JSBSim sends comma-separated values ending with a newline
        raw_string = data.decode('utf-8').strip()
        
        # JSBSim ALWAYS sends 'sim-time-sec' as the very first column!
        values = raw_string.split(',')
        
        # DEBUG: Print the raw string if we aren't getting the full 11 columns yet
        if len(values) > 6 and len(values) < 11:
            print(f"DEBUG - Received {len(values)} columns: {raw_string}")
            
        if len(values) >= 6:
            time_sec = float(values[0])
            lift_kg = abs(float(values[1])) * 0.453592
            drag_kg = abs(float(values[2])) * 0.453592
            alpha = float(values[3])
            beta = float(values[4])
            speed_ms = float(values[5]) * 0.514444
            
            output_str = f"Lift: {lift_kg:6.2f} kg | Drag: {drag_kg:6.2f} kg | AoA: {alpha:5.1f}° | Speed: {speed_ms:5.1f} m/s"
            
            # If using the NEW Generator output with Propulsion, Atmosphere & G-Force
            if len(values) >= 13:
                thrust_kg = float(values[6]) * 0.453592
                rpm = float(values[7])
                
                # JSBSim 'power-hp' is MECHANICAL SHAFT POWER. It inherently includes
                # propeller aerodynamic efficiency losses (via the APC tables).
                # However, it does NOT include motor electrical heat loss or ESC efficiency.
                # To find true battery draw, we divide the shaft power by the electrical efficiency (~85%).
                mechanical_watts = float(values[8]) * 745.7 # Convert HP to Watts
                electrical_watts = mechanical_watts / 0.85  # Factoring in 85% electrical efficiency
                
                l_over_d = (lift_kg / drag_kg) if drag_kg > 0 else 0.0
                g_force = -float(values[12]) # JSBSim Z is down, so invert to make +1G upright
                output_str += f" || Thrust: {thrust_kg:5.2f} kg | Batt Drain: {electrical_watts:5.0f} W | RPM: {rpm:4.0f} | L/D: {l_over_d:5.1f} | G-Force: {g_force:5.2f} G"
                
            print(output_str)
        else:
            print(raw_string)

except KeyboardInterrupt:
    print("\nStopped listening.")
