#!/usr/bin/env python3
"""Standalone extinguish-sequence test.

Connects to the Arduino, waits STARTUP_DELAY seconds (time to position the
rover in front of a flame), then runs the full two-phase pump sweep using only
the serial link — no camera, no YOLO, no Flask required.

Usage (from pi_code/):
    python3 test/extinguish_test.py
    python3 test/extinguish_test.py /dev/ttyACM0   # force a port
"""

from __future__ import annotations

import os
import sys
import time

# Allow running from pi_code/ or from pi_code/test/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rover.config import CONFIG
from rover.protocol import STOP, turn_l, turn_r
from rover.serial_link import SerialLink

STARTUP_DELAY = 8   # seconds to wait before starting

# Derive per-degree timing from the calibrated 90° constant (same as autonomy.py)
_TURN_90_MS  = CONFIG.autonomy.turn_90_align_ms
_SPD_BASE    = CONFIG.motion.align     # the speed TURN_90_ALIGN_MS was measured at

_SPD_SLOW    = 30
_SPD_FAST    = 70
_SETTLE_SLOW = 0.10   # seconds between turns (slow phase)
_SETTLE_FAST = 0.08   # seconds between turns (fast phase)
_PAUSE_S     = 1.5    # seconds between phases


def _deg_s(degrees: float, speed: int) -> float:
    """Seconds of motor-on time for the given angle at the given PWM speed."""
    return (_TURN_90_MS / 90) * (_SPD_BASE / speed) * degrees / 1000.0


def _send(link: SerialLink, cmd: str, label: str = "") -> None:
    ok = link.send(cmd)
    print(f"  {'✓' if ok else '✗'}  {label or cmd}")


def _sweep(link: SerialLink, speed: int, settle: float) -> None:
    """Oscillating sweep: +5° -10° +10° -10° +10° -5° → returns to start."""
    d5  = _deg_s(5,  speed)
    d10 = _deg_s(10, speed)

    _send(link, turn_r(speed), f"TURN_R {speed}  +5°   ({d5*1000:.0f} ms)");  time.sleep(d5)
    _send(link, STOP);                                                           time.sleep(settle)
    _send(link, turn_l(speed), f"TURN_L {speed}  -10°  ({d10*1000:.0f} ms)"); time.sleep(d10)
    _send(link, STOP);                                                           time.sleep(settle)
    _send(link, turn_r(speed), f"TURN_R {speed}  +10°  ({d10*1000:.0f} ms)"); time.sleep(d10)
    _send(link, STOP);                                                           time.sleep(settle)
    _send(link, turn_l(speed), f"TURN_L {speed}  -10°  ({d10*1000:.0f} ms)"); time.sleep(d10)
    _send(link, STOP);                                                           time.sleep(settle)
    _send(link, turn_r(speed), f"TURN_R {speed}  +10°  ({d10*1000:.0f} ms)"); time.sleep(d10)
    _send(link, STOP);                                                           time.sleep(settle)
    _send(link, turn_l(speed), f"TURN_L {speed}  -5°   ({d5*1000:.0f} ms)");  time.sleep(d5)
    _send(link, STOP)


def main() -> None:
    print("[extinguish_test] connecting to Arduino…")
    link = SerialLink(CONFIG.serial,
                      on_log=lambda m, c="": print(f"  serial: {m}"))
    link.connect(sys.argv[1] if len(sys.argv) > 1 else None)
    if not link.connected:
        print("✗  No Arduino found. Plug it in or pass the port as argv[1].")
        sys.exit(1)

    print(f"[extinguish_test] {STARTUP_DELAY}s startup delay — position rover in front of fire…")
    for i in range(STARTUP_DELAY, 0, -1):
        print(f"  {i}…", end="\r", flush=True)
        time.sleep(1)
    print()

    # ── Phase 1: slow sweep ───────────────────────────────────────────────────
    print(f"── Phase 1  spd={_SPD_SLOW}  pump ON ───────────────────────────")
    _send(link, "PUMP_ON", "PUMP ON")
    _sweep(link, _SPD_SLOW, _SETTLE_SLOW)
    _send(link, "PUMP_OFF", "PUMP OFF")

    print(f"── pause {_PAUSE_S:.1f}s ──────────────────────────────────────────")
    time.sleep(_PAUSE_S)

    # ── Phase 2: fast sweep ───────────────────────────────────────────────────
    print(f"── Phase 2  spd={_SPD_FAST}  pump ON ───────────────────────────")
    _send(link, "PUMP_ON", "PUMP ON")
    _sweep(link, _SPD_FAST, _SETTLE_FAST)
    _send(link, "PUMP_OFF", "PUMP OFF")

    # ── Done ──────────────────────────────────────────────────────────────────
    print("── done — STOP ─────────────────────────────────────────────────")
    _send(link, STOP)
    link.close()
    print("[extinguish_test] finished.")


if __name__ == "__main__":
    main()
