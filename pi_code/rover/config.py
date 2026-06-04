#!/usr/bin/env python3
"""Central configuration — every tunable constant lives here.

This is the one file to edit when fine-tuning the rover. Constants are grouped
by concern into frozen dataclasses, so a typo'd field fails loudly instead of
silently shadowing a global.

Nothing in here does I/O or imports heavy deps — safe to import anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Repo-relative anchor so paths work regardless of the cwd the server runs from.
PKG_DIR = Path(__file__).resolve().parent          # .../pi_code/rover
PI_DIR  = PKG_DIR.parent                            # .../pi_code


# ── Serial (Arduino link) ─────────────────────────────────────────────────────
@dataclass(frozen=True)
class SerialCfg:
    # Probed in order; first existing path wins (override with --serial).
    ports: tuple[str, ...] = ("/dev/ttyUSB0", "/dev/ttyACM0",
                              "/dev/ttyUSB1", "/dev/ttyACM1")
    baud: int = 115200
    timeout_s: float = 1.0


# ── Vision (camera + YOLO) ────────────────────────────────────────────────────
@dataclass(frozen=True)
class VisionCfg:
    model_path: Path = PI_DIR / "models" / "best.pt"
    hf_repo: str = "SalahALHaismawi/yolov26-fire-detection"
    hf_file: str = "best.pt"
    conf: float = 0.60                 # min detection confidence
    imgsz: int = 256                   # inference size (Pi-safe; 320+ risks OOM)
    every_n: int = 5                   # run YOLO every Nth frame, reuse cache
    labels: frozenset[str] = frozenset({"fire"})   # only these are tracked
    mjpeg_quality: int = 55            # JPEG encode quality for the stream


# ── Motion speeds (PWM 0-255, sent as "CMD,SPEED") ────────────────────────────
@dataclass(frozen=True)
class MotionCfg:
    align: int = 50         # slow + precise while centering (turns only)
    approach: int = 200     # fast forward toward fire (far out)
    approach_slow: int = 80 # forward in the final stretch before docking
    scan: int = 80          # 360° step-scan spin (bumped — recalibrate turn_90_scan_ms)
    idle: int = 200         # free-roam / idle wandering
    dock: int = 30          # fwd/rev nudges while converging on the dock target


# ── Autonomy (alignment + approach + roam FSM) ────────────────────────────────
@dataclass(frozen=True)
class AutonomyCfg:
    # Turn calibration — ONE measured datum drives every turn duration.
    # Rig measurement: a 90° pivot at full PWM (255) takes turn_90_max_ms.
    # Duration is assumed linear in both speed and angle, so for any turn:
    #     turn_ms = turn_90_max_ms * (255 / speed) * (deg / 90)
    # (e.g. 90° @ speed 50 → 6120ms, @ 80 → 3825ms, @ 200 → 1530ms.)
    turn_90_max_ms: float = 1200       # 90° at PWM 255 — MEASURE on rig

    # Alignment tuning
    alignment_threshold: int = 40      # px from center = "centered" (dead zone)
    realign_threshold: int = 80        # px drift during approach/dock before re-center
    camera_fov: float = 55.0           # camera horizontal FOV (degrees)
    settle_time: float = 0.35          # s stopped after a turn before re-deciding
    min_turn_ms: float = 60            # floor so tiny turns still move the motors
    fire_lost_grace: float = 5.0       # s fire must stay gone before any search
    engaged_grace_s: float = 12.0      # s a committed fire may stay lost before giving up

    # Stepped scan (stop-and-look 360° — camera held still while YOLO runs)
    scan_step_deg: int = 30            # ° turned per scan step (360/step = # of looks)
    scan_dwell_s: float = 1.5          # s stopped per step so detection sees clean frames

    # Approach + docking tuning
    pump_start_cm: int = 20            # front distance to PUMP_ON + hand off to docking
    dock_commit_cm: int = 20           # at/below this, docking ignores the camera (fire
                                       #   detection is unreliable this close) and drives
                                       #   on the front sensor alone to the target
    approach_slow_cm: int = 50         # front distance to drop from fast to slow approach
    approach_timeout: float = 8.0      # s max forward without docking (safety)
    dock_target_cm: int = 10           # closed-loop front-distance target before extinguish
    dock_tol_cm: int = 2               # ± band around target counted as "docked" (8–12cm)
    dock_nudge_ms: float = 220         # fwd/rev pulse length — longer = more ground per nudge
    dock_settle_ms: float = 120        # stop/settle (sensor read) between nudges — kept short
    dock_confirm_n: int = 1            # in-band reads to extinguish (sensor is reliable → 1)
    dock_timeout_s: float = 12.0       # safety: extinguish at current range if not converged

    # Free-roam tuning
    obstacle_cm: int = 30              # front distance counted as blocking
    side_cm: int = 30                  # side distance above this = "free" to turn
    roam_scan_interval: float = 10.0   # s of roaming between periodic 360 re-scans

    @property
    def half_fov(self) -> float:
        """Half the horizontal FOV — maps to half the frame width."""
        return self.camera_fov / 2.0


# ── Web server ────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ServerCfg:
    host: str = "0.0.0.0"
    port: int = 5000
    sensor_emit_hz: int = 10           # max WebSocket sensor pushes / sec
    max_speed: int = 255               # default speed for manual motion commands


# ── Top-level bundle ──────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RoverConfig:
    serial: SerialCfg = field(default_factory=SerialCfg)
    vision: VisionCfg = field(default_factory=VisionCfg)
    motion: MotionCfg = field(default_factory=MotionCfg)
    autonomy: AutonomyCfg = field(default_factory=AutonomyCfg)
    server: ServerCfg = field(default_factory=ServerCfg)


# Default singleton — import and use directly, or build a custom RoverConfig().
CONFIG = RoverConfig()
