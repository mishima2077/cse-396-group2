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
  3. Fire centered   → drive forward toward it (FWD: fast far out, slow near).
  4. Front ≤ PUMP_START_CM → STOP, PUMP_ON, hand off to DOCKING.
  5. DOCKING → closed-loop fwd/rev nudges until front == DOCK_TARGET_CM ± tol,
               confirmed over DOCK_CONFIRM_N reads → EXTINGUISHING.
  6. EXTINGUISHING → fixed run-to-completion sweep.
  7. Extinguish done → reverse ≈10cm → 360° re-scan → PARKED (stop, wait for fire).
  During approach/dock, if the fire drifts off-center it stops and re-centers,
  then resumes. Once a fire is acquired the rover is "engaged" and tolerates a
  much longer loss (ENGAGED_GRACE_S) before giving up; only then does it scan
  360° (stop-and-look steps) and, failing that, free-roam.

All tunables live in rover/config.py; the names below are thin aliases.
"""

import time

from rover.config import CONFIG
from rover.protocol import STOP, SPEED_MAX, fwd as _fwd, rev as _rev, turn_l as _turn_l, turn_r as _turn_r

_M = CONFIG.motion
_A = CONFIG.autonomy

# ── Motor speeds ──────────────────────────────────────────────────────────────
SPEED_ALIGN         = _M.align
SPEED_APPROACH      = _M.approach
SPEED_APPROACH_SLOW = _M.approach_slow
SPEED_SCAN          = _M.scan
SPEED_IDLE          = _M.idle
SPEED_DOCK          = _M.dock        # extra-slow fwd/rev pulses for closed-loop docking

# ── Turn timing ───────────────────────────────────────────────────────────────
# Everything derives from one rig datum (90° at full PWM takes TURN_90_MAX_MS),
# assuming linear scaling in both speed and angle.
TURN_90_MAX_MS = _A.turn_90_max_ms

def turn_ms(speed, deg=90.0):
    """Motor-on time (ms) for a `deg`° pivot at PWM `speed`.

    Linear in both: slower speed → longer, smaller angle → shorter:
        t = TURN_90_MAX_MS * (SPEED_MAX / speed) * (deg / 90)
    """
    return TURN_90_MAX_MS * (SPEED_MAX / max(1, speed)) * (deg / 90.0)

TURN_90_ALIGN_MS = turn_ms(SPEED_ALIGN)         # 90° align/extinguish-sweep speed
TURN_90_IDLE_MS  = turn_ms(SPEED_IDLE)          # 90° roam-avoidance turn
TURN_180_IDLE_MS = turn_ms(SPEED_IDLE, 180.0)   # 180° roam U-turn

# ── Alignment tuning ──────────────────────────────────────────────────────────
ALIGNMENT_THRESHOLD = _A.alignment_threshold
REALIGN_THRESHOLD   = _A.realign_threshold
CAMERA_FOV          = _A.camera_fov
HALF_FOV            = _A.half_fov
SETTLE_TIME         = _A.settle_time
MIN_TURN_MS         = _A.min_turn_ms
FIRE_LOST_GRACE     = _A.fire_lost_grace
ENGAGED_GRACE_S     = _A.engaged_grace_s

# ── Stepped scan tuning ───────────────────────────────────────────────────────
SCAN_STEP_DEG = _A.scan_step_deg
SCAN_DWELL_S  = _A.scan_dwell_s
SCAN_STEP_MS  = turn_ms(SPEED_SCAN, SCAN_STEP_DEG)        # motor-on time per step
SCAN_STEPS    = max(1, round(360 / SCAN_STEP_DEG))        # # of stop-and-look steps

# ── Approach + docking tuning ─────────────────────────────────────────────────
PUMP_START_CM    = _A.pump_start_cm
DOCK_COMMIT_CM   = _A.dock_commit_cm
APPROACH_SLOW_CM = _A.approach_slow_cm
APPROACH_TIMEOUT = _A.approach_timeout
DOCK_TARGET_CM   = _A.dock_target_cm
DOCK_TOL_CM      = _A.dock_tol_cm
DOCK_NUDGE_MS    = _A.dock_nudge_ms
DOCK_SETTLE_MS   = _A.dock_settle_ms
DOCK_CONFIRM_N   = _A.dock_confirm_n
DOCK_TIMEOUT_S   = _A.dock_timeout_s

# ── Free-roam tuning ──────────────────────────────────────────────────────────
OBSTACLE_CM         = _A.obstacle_cm
SIDE_CM             = _A.side_cm
ROAM_SCAN_INTERVAL  = _A.roam_scan_interval

# ── Extinguishing sequence ────────────────────────────────────────────────────
# ms derived from the alignment calibration: (deg / 90) * TURN_90_ALIGN_MS.
_EXT_DEG         = 10    # ° per step — only value to tune on the rig
_EXT_MS          = int((_EXT_DEG / 90.0) * TURN_90_ALIGN_MS)  # computed once
_EXT_SPD_SLOW    = 70    # PWM for phase 1
_EXT_SPD_FAST    = 100    # PWM for phase 2
_EXT_SETTLE_SLOW = 15   # ms pause between turns (slow phase)
_EXT_SETTLE_FAST = 5    # ms pause between turns (fast phase)
_EXT_PAUSE_MS    = 150  # ms gap between phases
_EXT_CORRECT_MS  = _EXT_MS/2  # final right-nudge to hit true center — tune on rig
_EXT_SPD_DRIVE   = 70    # PWM for forward/reverse phase 3
_EXT_DRIVE_MS    = _EXT_MS   # ms per fwd/rev step — tune on rig
_EXT_SETTLE_DRIVE = 10  # ms pause between fwd/rev steps
_EXT_BACKOFF_MS  = 1000  # ms reverse ≈ 10cm back-off after extinguish — tune on rig

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
    ("PUMP_ON",  0,       None),
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
    ("PUMP_OFF", 0,       None),
    # ── Back-off: reverse ≈10cm so the 360° re-scan starts clear of the fire ──
    ("REV",      _EXT_BACKOFF_MS, _EXT_SPD_DRIVE),
    ("STOP",     0,       None),
]


def deviation_to_turn_ms(deviation_px, frame_half_w):
    """Pixel deviation from center → motor turn duration (ms) + angle (deg).
    Duration is the time to pivot `angle`° at SPEED_ALIGN (turns happen slow)."""
    angle = (abs(deviation_px) / frame_half_w) * HALF_FOV
    return max(MIN_TURN_MS, turn_ms(SPEED_ALIGN, angle)), angle


class Aligner:
    """Stateful, non-blocking align + approach + extinguish decider.

    Call update() once per video frame with the fire deviation and the latest
    distance sensors. Returns the motor command to send (str) or None.
    """

    IDLE          = "IDLE"
    TURNING       = "TURNING"
    SETTLING      = "SETTLING"
    APPROACH      = "APPROACH"
    DOCKING       = "DOCKING"        # closed-loop fwd/rev nudges to DOCK_TARGET_CM ± tol
    ARRIVED       = "ARRIVED"        # log-only label; immediately enters EXTINGUISHING
    EXTINGUISHING = "EXTINGUISHING"
    SCANNING      = "SCANNING"       # 360° stop-and-look sweep looking for fire
    ROAMING       = "ROAMING"        # free-roam wander with obstacle avoidance
    PARKED        = "PARKED"         # mission done — hold still until fire returns

    def __init__(self, logger=None):
        # logger(msg: str, cls: str) — optional, mirrors decisions to dashboard
        self._log = logger or (lambda msg, cls="info": None)
        self.state = self.IDLE
        self.turn_end = 0.0          # wall-clock time the current turn should stop
        self.settle_end = 0.0        # wall-clock time the settle window ends
        self.approach_start = 0.0   # wall-clock time the current approach began
        self.last_sent = None        # last command returned (avoids spam)
        # search/roam phase machinery (all wall-clock, non-blocking)
        self.scan_steps_left = 0     # stop-and-look steps remaining in the 360° sweep
        self.scan_phase = "turn"     # "turn" | "look" within a scan step
        self.phase_end = 0.0         # wall-clock end of the current scan/roam phase
        self.roam_phase = "drive"    # "drive" | "turn" within roaming
        self.roam_clear_start = 0.0  # when the current clear forward run began
        self.fire_lost_since = None  # wall-clock when fire was last lost (grace timer)
        self._engaged = False        # committed to a fire → tolerate long losses
        # extinguish sequence state
        self._ext_step = 0
        self._ext_step_start = 0.0
        self._ext_phase = 0          # phase counter for logging (incremented per PUMP_ON)
        self._pump_armed = False     # pump fired at the dock hand-off
        self._scan_then_stop = False # next 360° scan ends in STOP (not roam)
        # closed-loop docking state
        self.dock_phase = "settle"   # "move" (pulsing) | "settle" (stopped, reading)
        self.dock_end = 0.0          # wall-clock end of the current dock phase
        self.dock_confirm = 0        # consecutive in-band reads so far
        self.dock_start = 0.0        # wall-clock dock entry (for the safety timeout)
        self._dock_committed = False # latched once inside DOCK_COMMIT_CM → ignore camera

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
        self._engaged = False
        self._ext_step = 0
        self._ext_step_start = 0.0
        self._ext_phase = 0
        self._pump_armed = False
        self._scan_then_stop = False
        self.dock_phase = "settle"
        self.dock_end = 0.0
        self.dock_confirm = 0
        self.dock_start = 0.0
        self._dock_committed = False

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
            self._engaged = True                        # commit — tolerate long losses
            if self.state in (self.SCANNING, self.ROAMING, self.PARKED):
                # snap out of search/park immediately and align this frame
                self.state = self.IDLE
                self.last_sent = "STOP"
                self._log("🔥 fire spotted — re-engage → align", "info")
        elif self.fire_lost_since is None:
            self.fire_lost_since = now                  # start grace countdown

        # ── Run the active search/roam phase machine (only when no fire) ─────
        if self.state == self.SCANNING:
            return self._scan_tick(now)
        if self.state == self.ROAMING:
            return self._roam_tick(now, center, left, right)
        if self.state == self.PARKED:
            return None    # mission done — hold still; exits only when fire returns

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

        # ── APPROACH: drive forward (fast far out, slow near), watch fire ────
        if self.state == self.APPROACH:
            if not has_fire:
                return self._go(self.IDLE, "STOP",
                                "✋ fire lost during approach — STOP", "warn")
            if abs(deviation) > REALIGN_THRESHOLD:
                return self._go(self.IDLE, "STOP",
                                f"↩ drifted dev={deviation:+d}px — STOP & re-center", "warn")
            if (now - self.approach_start) > APPROACH_TIMEOUT:
                return self._go(self.IDLE, "STOP",
                                f"⏱ approach timeout ({APPROACH_TIMEOUT}s) — STOP (front={center}cm)", "warn")
            # Reached docking range → STOP the fast approach, hand off to closed-loop docking.
            if center > 0 and center <= PUMP_START_CM:
                return self._start_dock(now, center)
            # Two-tier speed: full speed far out, slow once inside APPROACH_SLOW_CM
            # (0 = no echo = still far) so we never barrel into the dock zone fast.
            spd = SPEED_APPROACH if (center == 0 or center > APPROACH_SLOW_CM) else SPEED_APPROACH_SLOW
            fwd = _fwd(spd)
            if self.last_sent != fwd:
                self.last_sent = fwd
                return fwd
            return None

        # ── DOCKING: closed-loop fwd/rev nudges to converge on DOCK_TARGET_CM ─
        if self.state == self.DOCKING:
            # Latch "committed" once inside the commit range: this close the camera
            # is unreliable (the fire fills or leaves the frame), so we stop trusting
            # it and drive on the front sensor alone — push to target, then extinguish.
            if not self._dock_committed and 0 < center <= DOCK_COMMIT_CM:
                self._dock_committed = True
                self._log(f"🔒 dock committed at front={center}cm ≤ {DOCK_COMMIT_CM}cm — "
                          f"sensor-only to {DOCK_TARGET_CM}cm (camera ignored)", "info")
            # While NOT yet committed (farther out) the camera is trusted: abandon
            # on fire loss or big drift so we re-acquire/re-center before closing in.
            if not self._dock_committed:
                if not has_fire:
                    self._pump_armed = False
                    self.state = self.IDLE
                    self.last_sent = "PUMP_OFF"
                    self._log("✋ fire lost during docking — PUMP_OFF then STOP", "warn")
                    return "PUMP_OFF"
                if abs(deviation) > REALIGN_THRESHOLD:
                    self._pump_armed = False
                    return self._go(self.IDLE, "PUMP_OFF",
                                    f"↩ drifted dev={deviation:+d}px while docking — PUMP_OFF & re-center", "warn")
            if (now - self.dock_start) > DOCK_TIMEOUT_S:
                self._log(f"⏱ dock timeout ({DOCK_TIMEOUT_S}s) — extinguish at front={center}cm", "warn")
                return self._start_extinguish(now)
            # Arm the pump once, after the entry STOP has halted the fast approach.
            if not self._pump_armed:
                self._pump_armed = True
                self.dock_phase = "settle"
                self.dock_end = now + DOCK_SETTLE_MS / 1000.0
                self.last_sent = "PUMP_ON"
                return "PUMP_ON"
            # Mid nudge → keep moving until the pulse ends, then stop to read.
            if self.dock_phase == "move":
                if now >= self.dock_end:
                    self.dock_phase = "settle"
                    self.dock_end = now + DOCK_SETTLE_MS / 1000.0
                    self.last_sent = "STOP"
                    return "STOP"
                return None
            # Settling — let the sonar stabilise before reading.
            if now < self.dock_end:
                return None
            # Settle done → evaluate the front reading.
            if center <= 0:                          # no echo this read → settle again
                self.dock_end = now + DOCK_SETTLE_MS / 1000.0
                return None
            high = DOCK_TARGET_CM + DOCK_TOL_CM
            low  = DOCK_TARGET_CM - DOCK_TOL_CM
            if low <= center <= high:                # inside the band → confirm
                self.dock_confirm += 1
                if self.dock_confirm >= DOCK_CONFIRM_N:
                    self._log(f"✅ DOCKED — front={center}cm "
                              f"(target {DOCK_TARGET_CM}±{DOCK_TOL_CM}) → extinguish", "info")
                    return self._start_extinguish(now)
                self.dock_end = now + DOCK_SETTLE_MS / 1000.0   # hold for another read
                return None
            # Out of band → reset confirmation and nudge toward the target.
            self.dock_confirm = 0
            self.dock_phase = "move"
            self.dock_end = now + DOCK_NUDGE_MS / 1000.0
            if center > high:
                cmd = _fwd(SPEED_DOCK)
                self._log(f"🐢 dock front={center}cm > {high} → fwd nudge", "info")
            else:
                cmd = _rev(SPEED_DOCK)
                self._log(f"🐢 dock front={center}cm < {low} → rev nudge", "info")
            self.last_sent = cmd
            return cmd

        # ── IDLE: decide based on current target ─────────────────────────────
        if not has_fire:
            # Hold while within grace; a committed (engaged) fire gets a much
            # longer leash so the camera keeps trying to re-acquire before search.
            grace = ENGAGED_GRACE_S if self._engaged else FIRE_LOST_GRACE
            if (now - self.fire_lost_since) < grace:
                if self.last_sent != "STOP":
                    self.last_sent = "STOP"
                    return "STOP"
                return None
            # Grace expired → drop the commitment and start a 360 scan; else roam.
            self._engaged = False
            return self._start_scan(now)

        if abs(deviation) <= ALIGNMENT_THRESHOLD:
            # Centered, already inside docking range → converge precisely first.
            if center > 0 and center <= PUMP_START_CM:
                return self._start_dock(now, center)
            # Centered, still far → drive in.
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
    _EXT_PHASE_NAMES = {1: "slow sweep", 2: "fast sweep", 3: "fwd/rev drive"}

    def _start_extinguish(self, now):
        """Enter EXTINGUISHING and fire the first step immediately."""
        self.state = self.EXTINGUISHING
        self._ext_step = 0
        self._ext_step_start = now
        self._ext_phase = 1
        n = len(_EXT_SEQUENCE)
        self._log(f"🚿 ENTER EXTINGUISHING — {n} fixed steps · Phase 1 (slow sweep) · pump ON", "info")
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
        """Advance the FIXED extinguish choreography one step.

        Runs to completion, uninterrupted — no sensors, no nudges. Each step
        plays for its hardcoded duration, then the next begins. Detailed logs
        mark every phase and motion so the sequence is fully traceable.
        """
        _, duration_ms, _ = _EXT_SEQUENCE[self._ext_step]
        if (now - self._ext_step_start) < duration_ms / 1000.0:
            return None  # current step still playing — hold (send nothing)

        # Current step done → advance to the next.
        self._ext_step += 1
        if self._ext_step >= len(_EXT_SEQUENCE):
            self._pump_armed = False
            self._engaged = False           # fire dealt with — drop commitment
            self._scan_then_stop = True
            self._log("✅ EXTINGUISH complete — pump off, backed off → 360° re-scan then STOP", "info")
            return self._start_scan(now)

        self._ext_step_start = now
        step = _EXT_SEQUENCE[self._ext_step]
        action, _, spd = step

        # Milestone banners + per-motion trace.
        if action == "PUMP_ON":
            self._ext_phase += 1
            name = self._EXT_PHASE_NAMES.get(self._ext_phase, "sweep")
            self._log(f"🚿 Phase {self._ext_phase} ({name}) — pump ON", "info")
        elif action == "PUMP_OFF":
            self._log(f"🚿 Phase {self._ext_phase} done — pump OFF", "info")
        elif action == "WAIT":
            self._log(f"⏸ pause {_EXT_PAUSE_MS}ms before next phase", "info")
        elif action in ("TURN_L", "TURN_R", "FWD", "REV"):
            self._log(f"🚿 ext {self._ext_step + 1}/{len(_EXT_SEQUENCE)}: {action},{spd}", "info")

        cmd = self._ext_cmd(step)
        self.last_sent = cmd
        return cmd

    # ── DOCKING: closed-loop converge to DOCK_TARGET_CM before extinguishing ──
    def _start_dock(self, now, center):
        """Enter DOCKING: STOP the fast approach now, then converge in closed loop.

        The pump is armed on the *next* tick (after this STOP lands) so the rover
        is fully halted before water flows — this is what prevents the old
        "coast at FWD,200 through the settle window → slam" failure. Returns the
        entry STOP command."""
        self._pump_armed = False
        self._dock_committed = False
        self.dock_phase = "settle"
        self.dock_end = now + DOCK_SETTLE_MS / 1000.0
        self.dock_confirm = 0
        self.dock_start = now
        return self._go(self.DOCKING, STOP,
                        f"🛬 front={center}cm ≤ {PUMP_START_CM}cm → STOP, dock to "
                        f"{DOCK_TARGET_CM}±{DOCK_TOL_CM}cm", "info")

    # ── SCANNING: stepped stop-and-look 360° sweep ────────────────────────────
    def _start_scan(self, now):
        """Begin a 360° sweep as SCAN_STEPS discrete turn→look steps.

        Each step spins SCAN_STEP_DEG° then stops for SCAN_DWELL_S so YOLO sees
        motion-free frames. Fire is caught by preemption upstream (aborts the
        sweep instantly); a completed sweep with no fire → roam (or PARK after
        an extinguish)."""
        self.scan_steps_left = SCAN_STEPS
        self.scan_phase = "turn"
        self.phase_end = now + SCAN_STEP_MS / 1000.0
        return self._go(self.SCANNING, _turn_r(SPEED_SCAN),
                        f"🔍 step-scan {SCAN_STEPS}×{SCAN_STEP_DEG}° @spd{SPEED_SCAN}, "
                        f"dwell {SCAN_DWELL_S}s/step", "info")

    def _scan_tick(self, now):
        """Advance the stepped sweep. Fire = preemption upstream.

        turn phase: spin one step, then STOP and dwell.
        look phase: hold still through the dwell so detection runs on clean
        frames, then start the next step or finish (PARK after an extinguish,
        otherwise free-roam).
        """
        if self.scan_phase == "turn":
            if now >= self.phase_end:                   # step turn done → stop & look
                self.scan_phase = "look"
                self.phase_end = now + SCAN_DWELL_S
                self.last_sent = "STOP"
                return "STOP"
            return None                                 # still turning this step

        # look phase — camera held still for YOLO
        if now < self.phase_end:
            return None
        self.scan_steps_left -= 1
        if self.scan_steps_left <= 0:                   # full 360° covered, no fire
            if self._scan_then_stop:
                self._scan_then_stop = False
                return self._go(self.PARKED, STOP,
                                "🛑 post-extinguish 360° done → PARKED (idle, waiting for fire)", "info")
            return self._start_roam(now)
        self.scan_phase = "turn"                         # next step
        self.phase_end = now + SCAN_STEP_MS / 1000.0
        cmd = _turn_r(SPEED_SCAN)
        self.last_sent = cmd
        return cmd

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
