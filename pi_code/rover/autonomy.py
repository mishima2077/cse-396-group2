#!/usr/bin/env python3
"""Rover alignment + approach "brain" — pure decision logic, no I/O.

No camera, no serial here. Input: the fire's horizontal deviation (signed px
from frame center, or None if no fire) + distance sensors. Output: which motor
command to send (TURN_L / TURN_R / FWD / STOP) — or None.

All motion is NON-BLOCKING: the caller sends the returned command each frame
and keeps streaming video. Internally a small state machine driven by
wall-clock time + sensor readings, so no time.sleep ever stalls the caller.

Mission flow:
  1. No fire         → hold still (STOP).
  2. Fire off-center → rotate to center it (TURN_L/R).
  3. Fire centered   → drive forward toward it (FWD).
  4. Front sensor ≤ STOP_DISTANCE_CM → ARRIVED → EXTINGUISHING.
  5. EXTINGUISHING   → oscillating pump sweep (slow then fast) → IDLE.
  During approach, if the fire drifts off-center it stops and re-centers,
  then resumes. When fire is lost it scans 360°, then free-roams.

All tunables live in rover/config.py; the names below are thin aliases.
"""

import time

from rover.config import CONFIG
from rover.protocol import STOP, fwd as _fwd, rev as _rev, turn_l as _turn_l, turn_r as _turn_r

_M = CONFIG.motion
_A = CONFIG.autonomy

# ── Motor speeds ──────────────────────────────────────────────────────────────
SPEED_ALIGN    = _M.align
SPEED_APPROACH = _M.approach
SPEED_SCAN     = _M.scan
SPEED_IDLE     = _M.idle

# ── Hardcoded turn durations (motor-on time per rotation, ms) ─────────────────
TURN_90_ALIGN_MS = _A.turn_90_align_ms
TURN_90_IDLE_MS  = _A.turn_90_idle_ms
TURN_180_IDLE_MS = _A.turn_180_idle_ms
SCAN_360_MS      = _A.scan_360_ms

# ── Alignment tuning ──────────────────────────────────────────────────────────
ALIGNMENT_THRESHOLD = _A.alignment_threshold
REALIGN_THRESHOLD   = _A.realign_threshold
CAMERA_FOV          = _A.camera_fov
HALF_FOV            = _A.half_fov
SETTLE_TIME         = _A.settle_time
MIN_TURN_MS         = _A.min_turn_ms
FIRE_LOST_GRACE     = _A.fire_lost_grace

# ── Approach tuning ───────────────────────────────────────────────────────────
STOP_DISTANCE_CM    = _A.stop_distance_cm
APPROACH_TIMEOUT    = _A.approach_timeout

# ── Free-roam tuning ──────────────────────────────────────────────────────────
OBSTACLE_CM         = _A.obstacle_cm
SIDE_CM             = _A.side_cm
ROAM_SCAN_INTERVAL  = _A.roam_scan_interval

# ── Extinguishing sequence ────────────────────────────────────────────────────
# ms derived from the alignment calibration: (deg / 90) * TURN_90_ALIGN_MS.
_EXT_DEG         = 15    # ° per step — only value to tune on the rig
_EXT_MS          = int((_EXT_DEG / 90.0) * TURN_90_ALIGN_MS)  # computed once
_EXT_SPD_SLOW    = 50    # PWM for phase 1
_EXT_SPD_FAST    = 80    # PWM for phase 2
_EXT_SETTLE_SLOW = 150   # ms pause between turns (slow phase)
_EXT_SETTLE_FAST = 50    # ms pause between turns (fast phase)
_EXT_PAUSE_MS    = 1500  # ms gap between phases
_EXT_CORRECT_MS  = _EXT_MS/2  # final right-nudge to hit true center — tune on rig
_EXT_SPD_DRIVE   = 50    # PWM for forward/reverse phase 3
_EXT_DRIVE_MS    = _EXT_MS   # ms per fwd/rev step — tune on rig
_EXT_SETTLE_DRIVE = 100  # ms pause between fwd/rev steps

# Each step: (action, duration_ms, speed)
#   Pattern per phase: L R R L L R R L — 2 back-and-forth cycles, ends at center.
_EXT_SEQUENCE = [
    # ── Phase 1: slow ─────────────────────────────────────────────────────────
    ("PUMP_ON",  0,       None),
    ("TURN_L",   _EXT_MS, _EXT_SPD_SLOW),
    ("STOP",     _EXT_SETTLE_SLOW, None),
    ("TURN_R",   _EXT_MS, _EXT_SPD_SLOW),
    ("STOP",     _EXT_SETTLE_SLOW, None),
    ("TURN_R",   _EXT_MS, _EXT_SPD_SLOW),
    ("STOP",     _EXT_SETTLE_SLOW, None),
    ("TURN_L",   _EXT_MS, _EXT_SPD_SLOW),
    ("STOP",     _EXT_SETTLE_SLOW, None),
    ("TURN_L",   _EXT_MS, _EXT_SPD_SLOW),
    ("STOP",     _EXT_SETTLE_SLOW, None),
    ("TURN_R",   _EXT_MS, _EXT_SPD_SLOW),
    ("STOP",     _EXT_SETTLE_SLOW, None),
    ("TURN_R",   _EXT_MS, _EXT_SPD_SLOW),
    ("STOP",     _EXT_SETTLE_SLOW, None),
    ("TURN_L",   _EXT_MS, _EXT_SPD_SLOW),
    ("STOP",     0,       None),
    ("PUMP_OFF", 0,       None),
    ("WAIT",     _EXT_PAUSE_MS, None),
    # ── Phase 2: fast ─────────────────────────────────────────────────────────
    ("PUMP_ON",  0,       None),
    ("TURN_L",   _EXT_MS, _EXT_SPD_FAST),
    ("STOP",     _EXT_SETTLE_FAST, None),
    ("TURN_R",   _EXT_MS, _EXT_SPD_FAST),
    ("STOP",     _EXT_SETTLE_FAST, None),
    ("TURN_R",   _EXT_MS, _EXT_SPD_FAST),
    ("STOP",     _EXT_SETTLE_FAST, None),
    ("TURN_L",   _EXT_MS, _EXT_SPD_FAST),
    ("STOP",     _EXT_SETTLE_FAST, None),
    ("TURN_L",   _EXT_MS, _EXT_SPD_FAST),
    ("STOP",     _EXT_SETTLE_FAST, None),
    ("TURN_R",   _EXT_MS, _EXT_SPD_FAST),
    ("STOP",     _EXT_SETTLE_FAST, None),
    ("TURN_R",   _EXT_MS, _EXT_SPD_FAST),
    ("STOP",     _EXT_SETTLE_FAST, None),
    ("TURN_L",   _EXT_MS, _EXT_SPD_FAST),
    ("STOP",     0,       None),
    ("PUMP_OFF", 0,       None),
    ("TURN_R",   _EXT_CORRECT_MS, _EXT_SPD_SLOW),
    ("STOP",     0,       None),
    # ── Phase 3: forward / reverse ────────────────────────────────────────────
    # Pattern: F R R F F R R F — 2 cycles, ends at start position.
    ("FWD",      _EXT_DRIVE_MS, _EXT_SPD_DRIVE),
    ("STOP",     _EXT_SETTLE_DRIVE, None),
    ("REV",      _EXT_DRIVE_MS, _EXT_SPD_DRIVE),
    ("STOP",     _EXT_SETTLE_DRIVE, None),
    ("REV",      _EXT_DRIVE_MS, _EXT_SPD_DRIVE),
    ("STOP",     _EXT_SETTLE_DRIVE, None),
    ("FWD",      _EXT_DRIVE_MS, _EXT_SPD_DRIVE),
    ("STOP",     _EXT_SETTLE_DRIVE, None),
    ("FWD",      _EXT_DRIVE_MS, _EXT_SPD_DRIVE),
    ("STOP",     _EXT_SETTLE_DRIVE, None),
    ("REV",      _EXT_DRIVE_MS, _EXT_SPD_DRIVE),
    ("STOP",     _EXT_SETTLE_DRIVE, None),
    ("REV",      _EXT_DRIVE_MS, _EXT_SPD_DRIVE),
    ("STOP",     _EXT_SETTLE_DRIVE, None),
    ("FWD",      _EXT_DRIVE_MS, _EXT_SPD_DRIVE),
    ("STOP",     0,       None),
]


def deviation_to_turn_ms(deviation_px, frame_half_w):
    """Pixel deviation from center → motor turn duration (ms) + angle (deg).
    Duration uses the align-speed 90° time (turns happen at SPEED_ALIGN)."""
    angle = (abs(deviation_px) / frame_half_w) * HALF_FOV
    turn_ms = (angle / 90.0) * TURN_90_ALIGN_MS
    return max(MIN_TURN_MS, turn_ms), angle


class Aligner:
    """Stateful, non-blocking align + approach + extinguish decider.

    Call update() once per video frame with the fire deviation and the latest
    distance sensors. Returns the motor command to send (str) or None.
    """

    IDLE          = "IDLE"
    TURNING       = "TURNING"
    SETTLING      = "SETTLING"
    APPROACH      = "APPROACH"
    ARRIVED       = "ARRIVED"        # log-only label; immediately enters EXTINGUISHING
    EXTINGUISHING = "EXTINGUISHING"
    SCANNING      = "SCANNING"       # 360° sweep looking for fire
    ROAMING       = "ROAMING"        # free-roam wander with obstacle avoidance

    def __init__(self, logger=None):
        # logger(msg: str, cls: str) — optional, mirrors decisions to dashboard
        self._log = logger or (lambda msg, cls="info": None)
        self.state = self.IDLE
        self.turn_end = 0.0          # wall-clock time the current turn should stop
        self.settle_end = 0.0        # wall-clock time the settle window ends
        self.approach_start = 0.0   # wall-clock time the current approach began
        self.last_sent = None        # last command returned (avoids spam)
        # search/roam phase machinery (all wall-clock, non-blocking)
        self.scan_steps_left = 0
        self.scan_phase = "turn"     # "turn" | "look" within a scan step
        self.phase_end = 0.0         # wall-clock end of the current scan/roam phase
        self.roam_phase = "drive"    # "drive" | "turn" within roaming
        self.roam_clear_start = 0.0  # when the current clear forward run began
        self.fire_lost_since = None  # wall-clock when fire was last lost (grace timer)
        # extinguish sequence state
        self._ext_step = 0
        self._ext_step_start = 0.0

    def reset(self):
        """Reset FSM to IDLE — call when returning to auto mode after manual control."""
        self.state = self.IDLE
        self.turn_end = 0.0
        self.settle_end = 0.0
        self.approach_start = 0.0
        self.last_sent = None
        self.scan_steps_left = 0
        self.scan_phase = "turn"
        self.phase_end = 0.0
        self.roam_phase = "drive"
        self.roam_clear_start = 0.0
        self.fire_lost_since = None
        self._ext_step = 0
        self._ext_step_start = 0.0

    def _go(self, state, cmd, msg, cls="info"):
        """Transition to a state, log it, and return the command to send."""
        self.state = state
        self.last_sent = cmd
        if msg:
            self._log(msg, cls)
        return cmd

    def update(self, deviation, frame_w, sensors=None, now=None):
        """Decide the next motor command.

        deviation: signed px from center (+right / -left), or None if no fire.
        frame_w:   current frame width (px).
        sensors:   dict {left, center, right} in cm (center used for approach).
        now:       wall-clock seconds (defaults to time.time()).

        Returns: command string to send to Arduino, or None.
        """
        if now is None:
            now = time.time()
        if sensors is None:
            sensors = {}
        frame_half_w = frame_w // 2
        center = sensors.get("center", 0) or 0
        left   = sensors.get("left", 0) or 0
        right  = sensors.get("right", 0) or 0
        has_fire = deviation is not None

        # ── EXTINGUISHING runs to completion — nothing interrupts it ─────────
        if self.state == self.EXTINGUISHING:
            return self._extinguish_tick(now)

        # ── FIRE = HIGHEST PRIORITY — everything else is secondary ───────────
        if has_fire:
            self.fire_lost_since = None                 # reset grace timer
            if self.state in (self.SCANNING, self.ROAMING):
                # snap out of search immediately and align this frame
                self.state = self.IDLE
                self.last_sent = "STOP"
                self._log("🔥 fire spotted — abort search → align", "info")
        elif self.fire_lost_since is None:
            self.fire_lost_since = now                  # start grace countdown

        # ── Run the active search/roam phase machine (only when no fire) ─────
        if self.state == self.SCANNING:
            return self._scan_tick(now)
        if self.state == self.ROAMING:
            return self._roam_tick(now, center, left, right)

        # ── Finish an in-progress turn (non-blocking) ────────────────────────
        if self.state == self.TURNING:
            if now >= self.turn_end:
                self.state = self.SETTLING
                self.settle_end = now + SETTLE_TIME
                self.last_sent = "STOP"
                return "STOP"
            return None  # still turning, send nothing

        if self.state == self.SETTLING:
            if now < self.settle_end:
                return None  # let camera/YOLO catch up before re-deciding
            self.state = self.IDLE  # settled — fall through and reassess now

        # ── APPROACH: drive forward, watch fire + front sensor ───────────────
        if self.state == self.APPROACH:
            if not has_fire:
                return self._go(self.IDLE, "STOP",
                                "✋ fire lost during approach — STOP", "warn")
            if center > 0 and center <= STOP_DISTANCE_CM:
                self._log(f"✅ ARRIVED — front={center}cm → starting extinguish", "info")
                return self._start_extinguish(now)
            if abs(deviation) > REALIGN_THRESHOLD:
                return self._go(self.IDLE, "STOP",
                                f"↩ drifted dev={deviation:+d}px — STOP & re-center", "warn")
            if (now - self.approach_start) > APPROACH_TIMEOUT:
                return self._go(self.IDLE, "STOP",
                                f"⏱ approach timeout ({APPROACH_TIMEOUT}s) — STOP (front={center}cm)", "warn")
            fwd = _fwd(SPEED_APPROACH)
            if self.last_sent != fwd:
                self.last_sent = fwd
                return fwd
            return None

        # ── IDLE: decide based on current target ─────────────────────────────
        if not has_fire:
            # brief fire loss (flicker/frame-skip) → hold still, don't search yet
            if (now - self.fire_lost_since) < FIRE_LOST_GRACE:
                if self.last_sent != "STOP":
                    self.last_sent = "STOP"
                    return "STOP"
                return None
            # fire truly gone → start a 360 scan; nothing found → roam
            return self._start_scan(now)

        if abs(deviation) <= ALIGNMENT_THRESHOLD:
            # Centered — already at the fire?
            if center > 0 and center <= STOP_DISTANCE_CM:
                self._log(f"✅ ARRIVED — front={center}cm → starting extinguish", "info")
                return self._start_extinguish(now)
            # Centered, not there yet → start approaching
            self.approach_start = now
            return self._go(self.APPROACH, _fwd(SPEED_APPROACH),
                            f"🎯 centered dev={deviation:+d}px → APPROACH (front={center}cm) @spd{SPEED_APPROACH}", "info")

        # Off-center → start a proportional turn at slow align speed
        turn_ms, angle = deviation_to_turn_ms(deviation, frame_half_w)
        cmd = _turn_l(SPEED_ALIGN) if deviation < 0 else _turn_r(SPEED_ALIGN)
        self.turn_end = now + turn_ms / 1000.0
        return self._go(self.TURNING, cmd,
                        f"↺ dev={deviation:+d}px → {angle:.1f}° {cmd} for {turn_ms:.0f}ms", "info")

    # ── EXTINGUISHING: timed oscillating pump sweep ───────────────────────────
    def _start_extinguish(self, now):
        """Enter EXTINGUISHING and execute the first step immediately."""
        self.state = self.EXTINGUISHING
        self._ext_step = 0
        self._ext_step_start = now
        self._log("🚿 extinguish sequence started — slow sweep, pump ON", "info")
        cmd = self._ext_cmd(_EXT_SEQUENCE[0])
        self.last_sent = cmd
        return cmd

    def _ext_cmd(self, step):
        """Build the Arduino command for one extinguish step."""
        action, _, speed = step
        if action == "TURN_R":  return _turn_r(speed)
        if action == "TURN_L":  return _turn_l(speed)
        if action == "FWD":     return _fwd(speed)
        if action == "REV":     return _rev(speed)
        if action in ("STOP", "WAIT"):  return STOP
        return action  # "PUMP_ON" or "PUMP_OFF" passed through verbatim

    def _extinguish_tick(self, now):
        """Advance the extinguish sequence one tick. Called every frame."""
        action, duration_ms, _ = _EXT_SEQUENCE[self._ext_step]
        if (now - self._ext_step_start) < duration_ms / 1000.0:
            return None  # current step still running

        # Advance to the next step
        self._ext_step += 1
        if self._ext_step >= len(_EXT_SEQUENCE):
            return self._go(self.IDLE, STOP, "✅ Extinguish complete → IDLE", "info")

        self._ext_step_start = now
        step = _EXT_SEQUENCE[self._ext_step]
        action, _, _ = step

        if action == "WAIT":
            self._log(f"🚿 slow sweep done — pausing {_EXT_PAUSE_MS}ms", "info")
        elif action == "PUMP_ON" and self._ext_step > 1:
            self._log("🚿 fast sweep starting — pump ON", "info")

        cmd = self._ext_cmd(step)
        self.last_sent = cmd
        return cmd

    # ── SCANNING: one continuous 360° spin at scan speed ─────────────────────
    def _start_scan(self, now):
        """Spin a full 360° at scan speed. Fire is caught by preemption upstream
        (aborts the spin instantly); a completed spin with no fire → roam."""
        self.phase_end = now + SCAN_360_MS / 1000.0
        return self._go(self.SCANNING, _turn_r(SPEED_SCAN),
                        f"🔍 360° search spin @spd{SPEED_SCAN} ({SCAN_360_MS:.0f}ms)", "info")

    def _scan_tick(self, now):
        """Keep spinning until 360° done, then roam. Fire = preemption upstream."""
        if now >= self.phase_end:
            return self._start_roam(now)
        return None                                # still spinning, send nothing

    # ── ROAMING: wander forward, avoid obstacles, periodic re-scan ───────────
    def _start_roam(self, now):
        self.roam_phase = "drive"
        self.roam_clear_start = now   # anchor for the periodic 360 re-scan
        return self._go(self.ROAMING, _fwd(SPEED_IDLE), "🚶 free-roam — drive forward", "info")

    def _roam_tick(self, now, center, left, right):
        fwd       = _fwd(SPEED_IDLE)
        turn90_s  = TURN_90_IDLE_MS  / 1000.0
        turn180_s = TURN_180_IDLE_MS / 1000.0

        # finishing an avoidance turn? → reset scan timer
        if self.roam_phase == "turn":
            if now >= self.phase_end:
                self.roam_phase = "drive"
                self.roam_clear_start = now        # avoidance resets the 10s timer
                self.last_sent = fwd
                return fwd
            return None                            # still turning

        # driving forward — obstacle ahead? (0 = no echo = clear)
        if 0 < center <= OBSTACLE_CM:
            right_free = (right == 0) or (right > SIDE_CM)
            left_free  = (left == 0)  or (left > SIDE_CM)
            if right_free:
                self.roam_phase = "turn"
                self.phase_end = now + turn90_s
                return self._go(self.ROAMING, _turn_r(SPEED_IDLE),
                                f"⛔ front={center}cm → right free → 90° TURN_R", "warn")
            if left_free:
                self.roam_phase = "turn"
                self.phase_end = now + turn90_s
                return self._go(self.ROAMING, _turn_l(SPEED_IDLE),
                                f"⛔ front={center}cm → left free → 90° TURN_L", "warn")
            self.roam_phase = "turn"
            self.phase_end = now + turn180_s
            return self._go(self.ROAMING, _turn_r(SPEED_IDLE),
                            f"⛔ front={center}cm boxed in → 180° U-turn", "warn")

        # 10s of uninterrupted clear driving → 360 re-scan
        if (now - self.roam_clear_start) >= ROAM_SCAN_INTERVAL:
            self._log(f"⏱ {ROAM_SCAN_INTERVAL:.0f}s clear — 360° re-scan", "info")
            return self._start_scan(now)

        # keep cruising
        if self.last_sent != fwd:
            self.last_sent = fwd
            return fwd
        return None
