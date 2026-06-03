#!/usr/bin/env python3
"""
Simple command sender for the rover.
Sends motor, pump, and servo commands to Arduino via serial.

Usage:
    python3 command_sender.py [port] [baud]

Interactive mode:
    Enter commands:
      fwd, rev, left, right, stop
      pump_on, pump_off
      servo <0-180>
      exit

Default port: /dev/ttyUSB0 (auto-detect)
Default baud: 115200
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

def normalize_command(cmd):
    """Convert user input to Arduino command"""
    cmd = cmd.strip().upper()

    aliases = {
        'FWD': 'FWD',
        'F': 'FWD',
        'FORWARD': 'FWD',
        'REV': 'REV',
        'R': 'REV',
        'REVERSE': 'REV',
        'LEFT': 'TURN_L',
        'L': 'TURN_L',
        'TURN_L': 'TURN_L',
        'RIGHT': 'TURN_R',
        'RT': 'TURN_R',
        'TURN_R': 'TURN_R',
        'STOP': 'STOP',
        'S': 'STOP',
        'PUMP_ON': 'PUMP_ON',
        'PON': 'PUMP_ON',
        'PUMP_OFF': 'PUMP_OFF',
        'POFF': 'PUMP_OFF',
    }

    if cmd in aliases:
        return aliases[cmd]

    if cmd.startswith('SERVO ') or cmd.startswith('SRV '):
        parts = cmd.split()
        try:
            angle = int(parts[1])
            if 0 <= angle <= 180:
                return f"SERVO,{angle}"
            print(f"  ! Angle out of range: {angle} (must be 0-180)")
        except (ValueError, IndexError):
            print("  ! Usage: servo <0-180>")
        return None

    return None

def print_help():
    print("\nAvailable commands:")
    print("  fwd, f, forward      - Move forward")
    print("  rev, r, reverse      - Move backward")
    print("  left, l, turn_l      - Turn left")
    print("  right, rt, turn_r    - Turn right")
    print("  stop, s              - Stop motors")
    print("  pump_on, pon         - Start water pump")
    print("  pump_off, poff       - Stop water pump")
    print("  servo <0-180>        - Set hose servo angle")
    print("  srv <0-180>          - Set hose servo angle (short)")
    print("  help                 - Show this message")
    print("  exit, quit           - Exit program")
    print()

def main():
    # Parse arguments
    port = sys.argv[1] if len(sys.argv) > 1 else find_serial_port()
    baud = int(sys.argv[2]) if len(sys.argv) > 2 else 115200

    if not port:
        print("ERROR: Could not find serial port")
        print("Usage: python3 command_sender.py [port] [baud]")
        sys.exit(1)

    try:
        ser = serial.Serial(port, baud, timeout=1)
        print(f"Connected to {port} at {baud} baud")
        print_help()

        while True:
            try:
                cmd = input("rover> ").strip()

                if not cmd:
                    continue

                if cmd.lower() in ['exit', 'quit']:
                    print("Goodbye!")
                    break

                if cmd.lower() == 'help':
                    print_help()
                    continue

                # Normalize and send command
                arduino_cmd = normalize_command(cmd)
                if arduino_cmd:
                    message = arduino_cmd + '\n'
                    ser.write(message.encode())
                    print(f"  -> sent: {arduino_cmd}")
                else:
                    print(f"  ? Unknown command: {cmd}")
                    print(f"    Type 'help' for available commands")

            except KeyboardInterrupt:
                print("\n\nInterrupted. Stopping motors...")
                ser.write(b"STOP\n")
                break
            except Exception as e:
                print(f"Error: {e}")

    except serial.SerialException as e:
        print(f"ERROR: Could not open serial port {port}")
        print(f"  {e}")
        sys.exit(1)
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()

if __name__ == "__main__":
    main()
