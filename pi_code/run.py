#!/usr/bin/env python3
"""Launcher for the rover dashboard server.

    python3 run.py [--port 5001] [--no-yolo] [--no-align] [--serial /dev/ttyACM0]
"""

from rover.app import main

if __name__ == "__main__":
    main()
