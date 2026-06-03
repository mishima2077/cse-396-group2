#!/usr/bin/env python3
"""
Simple sensor data monitor for the rover.
Reads serial data from Arduino and prints formatted sensor values.

Usage:
    python3 sensor_monitor.py [port] [baud]

Default:
    port: /dev/ttyUSB0 (or /dev/ttyACM0)
    baud: 115200
"""

import serial
import sys
import time
from pathlib import Path

def find_serial_port():
    """Auto-detect Arduino serial port"""
    ports_to_try = [
        "/dev/ttyUSB0",
        "/dev/ttyACM0",
        "/dev/ttyUSB1",
        "/dev/ttyACM1",
    ]

    for port in ports_to_try:
        if Path(port).exists():
            return port

    return None

def parse_sensor_data(line):
    """
    Parse sensor data from Arduino.
    Format: D,<left>,<center>,<right>,<flame_analog>,<flame_digital>
    Returns: dict or None if parse fails
    """
    line = line.strip()
    if not line or line[0] != 'D':
        return None

    try:
        parts = line.split(',')
        if len(parts) != 6:
            return None

        return {
            'distance_left': int(parts[1]),
            'distance_center': int(parts[2]),
            'distance_right': int(parts[3]),
            'flame_analog': int(parts[4]),
            'flame_digital': int(parts[5]),
        }
    except (ValueError, IndexError):
        return None

def format_distance(dist_cm):
    """Format distance nicely with units"""
    if dist_cm == 0:
        return "  NONE  "
    return f"{dist_cm:3d}cm"

def print_sensor_data(data):
    """Pretty print sensor data"""
    dist_l = format_distance(data['distance_left'])
    dist_c = format_distance(data['distance_center'])
    dist_r = format_distance(data['distance_right'])

    flame_analog = data['flame_analog']
    flame_detected = "FIRE!" if data['flame_digital'] == 0 else "OK"

    print(f"  Left: {dist_l}  |  Center: {dist_c}  |  Right: {dist_r}  |  "
          f"Flame: {flame_analog:4d}  [{flame_detected}]")

def main():
    # Parse arguments
    port = sys.argv[1] if len(sys.argv) > 1 else find_serial_port()
    baud = int(sys.argv[2]) if len(sys.argv) > 2 else 115200

    if not port:
        print("ERROR: Could not find serial port")
        print("Usage: python3 sensor_monitor.py [port] [baud]")
        print("Example: python3 sensor_monitor.py /dev/ttyUSB0 115200")
        sys.exit(1)

    print(f"Opening {port} at {baud} baud...")

    try:
        ser = serial.Serial(port, baud, timeout=1)
        print(f"Connected! Reading sensor data...\n")
        print("┌─ Ultrasonic Distance (cm) ─┬─ Fire Sensor ─┐")
        print("│ Left | Center | Right       │ Raw  | Status │")
        print("├──────┼────────┼─────────────┼──────┼────────┤")

        while True:
            try:
                line = ser.readline().decode('utf-8', errors='ignore')

                if line:
                    data = parse_sensor_data(line)
                    if data:
                        print_sensor_data(data)
                    else:
                        print(f"  [unparseable: {line.strip()}]")

            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except Exception as e:
                print(f"  Error: {e}")
                time.sleep(0.1)

    except serial.SerialException as e:
        print(f"ERROR: Could not open serial port {port}")
        print(f"  {e}")
        sys.exit(1)
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()

if __name__ == "__main__":
    main()
