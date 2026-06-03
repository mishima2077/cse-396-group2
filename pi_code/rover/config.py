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
    align: int = 50        # slow + precise while centering (turns only)
    approach: int = 200    # forward toward fire
    scan: int = 50         # continuous 360° search-spin
    idle: int = 200        # free-roam / idle wandering


# ── Autonomy (alignment + approach + roam FSM) ────────────────────────────────
@dataclass(frozen=True)
class AutonomyCfg:
    # Hardcoded turn durations — MEASURE on rig at each speed, then edit (ms).
    turn_90_align_ms: float = 6120     # 90° at MotionCfg.align(50)
    turn_90_idle_ms: float = 1530      # 90° at MotionCfg.idle(200)
    turn_180_idle_ms: float = 3060     # 180° at MotionCfg.idle(200)
    scan_360_ms: float = 24480         # 360° at MotionCfg.scan(50)

    # Alignment tuning
    alignment_threshold: int = 40      # px from center = "centered" (dead zone)
    realign_threshold: int = 80        # px drift during approach before re-center
    camera_fov: float = 55.0           # camera horizontal FOV (degrees)
    settle_time: float = 0.35          # s stopped after a turn before re-deciding
    min_turn_ms: float = 60            # floor so tiny turns still move the motors
    fire_lost_grace: float = 1.0       # s fire must stay gone before any search

    # Approach tuning
    stop_distance_cm: int = 20         # front distance to stop in front of fire
    approach_timeout: float = 8.0      # s max forward without arriving (safety)

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
