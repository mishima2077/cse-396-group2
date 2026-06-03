#!/usr/bin/env python3
"""Arduino wire protocol — the single source of truth for the serial format.

Pi → Arduino (commands):
    <CMD>\\n          for STOP, PUMP_ON, PUMP_OFF
    <CMD>,<speed>\\n  for FWD, REV, TURN_L, TURN_R   (speed 0-255)

Arduino → Pi (telemetry, every 100 ms):
    D,<left>,<center>,<right>,<flame_analog>,<flame_digital>\\n

Both the autonomy FSM and the web command handler build commands through the
helpers here, so the wire format is defined in exactly one place.
"""

from __future__ import annotations

from dataclasses import dataclass

# ── Command vocabulary ────────────────────────────────────────────────────────
MOTION_CMDS = frozenset({"FWD", "REV", "TURN_L", "TURN_R"})   # take a speed arg
SIMPLE_CMDS = frozenset({"STOP", "PUMP_ON", "PUMP_OFF"})      # no speed arg

STOP = "STOP"

SPEED_MIN = 0
SPEED_MAX = 255


def clamp_speed(value) -> int:
    """Coerce anything to a valid PWM speed in [0, 255]."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return SPEED_MAX
    return max(SPEED_MIN, min(SPEED_MAX, v))


# ── Command builders ──────────────────────────────────────────────────────────
def fwd(speed) -> str:    return f"FWD,{clamp_speed(speed)}"
def rev(speed) -> str:    return f"REV,{clamp_speed(speed)}"
def turn_l(speed) -> str: return f"TURN_L,{clamp_speed(speed)}"
def turn_r(speed) -> str: return f"TURN_R,{clamp_speed(speed)}"


def motion(cmd: str, speed) -> str:
    """Build a 'CMD,SPEED' string for a known motion command (already upper)."""
    return f"{cmd},{clamp_speed(speed)}"


# ── Telemetry parsing ─────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SensorData:
    left: int       # cm, 0 = no echo (clear)
    center: int
    right: int
    flame_a: int    # ADC 0-1023
    flame_d: int    # 0 = fire detected (active LOW)

    def as_dict(self) -> dict:
        return {
            "left": self.left, "center": self.center, "right": self.right,
            "flame_a": self.flame_a, "flame_d": self.flame_d,
        }


# Neutral reading used before the first frame arrives (flame_d=1 → no fire).
NO_SENSOR_DATA = SensorData(left=0, center=0, right=0, flame_a=0, flame_d=1)


def parse_sensor_frame(line: str) -> SensorData | None:
    """Parse one 'D,...' telemetry line into SensorData, or None if malformed."""
    if not line.startswith("D,"):
        return None
    parts = line.split(",")
    if len(parts) != 6:
        return None
    try:
        return SensorData(
            left=int(parts[1]), center=int(parts[2]), right=int(parts[3]),
            flame_a=int(parts[4]), flame_d=int(parts[5]),
        )
    except ValueError:
        return None
