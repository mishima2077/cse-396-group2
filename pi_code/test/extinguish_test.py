#!/usr/bin/env python3
"""Extinguish sequence integration test.

Forces the Aligner FSM into EXTINGUISHING state and drives its update() loop
against the real Arduino — the exact same code path as production runtime.
Tune autonomy.py constants, re-run this, repeat until the arcs look right.

Usage (from pi_code/):
    python3 test/extinguish_test.py
    python3 test/extinguish_test.py /dev/ttyACM0   # force a port
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rover.autonomy import Aligner
from rover.config import CONFIG
from rover.serial_link import SerialLink

STARTUP_DELAY = 8   # seconds — time to position rover in front of fire
TICK_S        = 1 / 30  # 30 Hz — matches the video loop tick rate


def main() -> None:
    print("[extinguish_test] connecting to Arduino…")
    link = SerialLink(CONFIG.serial,
                      on_log=lambda m, _="": print(f"  serial: {m}"))
    link.connect(sys.argv[1] if len(sys.argv) > 1 else None)
    if not link.connected:
        print("✗  No Arduino found. Plug it in or pass the port as argv[1].")
        sys.exit(1)

    print(f"[extinguish_test] {STARTUP_DELAY}s startup — position rover in front of fire…")
    for i in range(STARTUP_DELAY, 0, -1):
        print(f"  {i}…", end="\r", flush=True)
        time.sleep(1)
    print()

    def log(msg, cls="info"):
        print(f"  [{cls}] {msg}")

    aligner = Aligner(logger=log)

    # Same call the FSM makes on ARRIVED — forces EXTINGUISHING immediately
    now = time.time()
    cmd = aligner._start_extinguish(now)
    if cmd:
        link.send(cmd)
        print(f"  -> {cmd}")

    # Drive the FSM until it finishes and returns to IDLE
    while aligner.state == aligner.EXTINGUISHING:
        time.sleep(TICK_S)
        now = time.time()
        cmd = aligner.update(None, 640, sensors={}, now=now)
        if cmd:
            link.send(cmd)
            print(f"  -> {cmd}")

    print("[extinguish_test] finished.")
    link.close()


if __name__ == "__main__":
    main()
