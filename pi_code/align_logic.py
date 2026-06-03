#!/usr/bin/env python3
"""
Rover alignment + approach "brain" — pure decision logic, no I/O.

No camera, no serial here. Input: where the fire is + distance sensors.
Output: which motor command to send (TURN_L / TURN_R / FWD / STOP) — or None.

All motion is NON-BLOCKING: the caller sends the returned command each frame
and keeps streaming video. Internally a small state machine driven by
wall-clock time + sensor readings, so no time.sleep ever stalls the video
thread.

Mission flow:
  1. No fire        → hold still (STOP).               [Phase 1]
  2. Fire off-center→ rotate to center it (TURN_L/R).  [Phase 1]
  3. Fire centered  → drive forward toward it (FWD).   [Phase 2]
  4. Front sensor ≤ STOP_DISTANCE_CM → stop (ARRIVED). [Phase 2]
  During approach, if the fire drifts off-center it stops and re-centers,
  then resumes. Side sensors are ignored for now.
"""

import time

# ── Motor speeds (new Arduino interface: "CMD,SPEED", 0-255) ──────────────────
SPEED_ALIGN    = 50    # slow + precise while centering (turns only)
SPEED_APPROACH = 200   # forward speed while driving toward fire
SPEED_SCAN  = 50    # continuous 360° search-spin speed
SPEED_IDLE  = 200   # free-roam / idle wandering speed

STOP = "STOP"   # stop takes no speed argument


def _fwd(speed):    return f"FWD,{int(speed)}"
def _turn_l(speed): return f"TURN_L,{int(speed)}"
def _turn_r(speed): return f"TURN_R,{int(speed)}"


# ── Hardcoded turn durations — MEASURE on rig at each speed, then edit ─────────
# Each = motor-on time for that rotation at its speed tier (ms).
TURN_90_ALIGN_MS = 6120    # 90° at SPEED_ALIGN(50)  — align centering turns
TURN_90_IDLE_MS  = 1530    # 90° at SPEED_IDLE(200)  — roam avoidance turns
TURN_180_IDLE_MS = 3060    # 180° at SPEED_IDLE(200) — roam u-turn
SCAN_360_MS      = 24480   # 360° at SPEED_SCAN(50)  — search spin  ← measure & fix

# ── Alignment tuning ──────────────────────────────────────────────────────────
ALIGNMENT_THRESHOLD = 40      # px from center counted as "centered" (dead zone)
REALIGN_THRESHOLD   = 80      # px drift during approach before re-centering
CAMERA_FOV          = 55      # camera horizontal field of view (degrees)
HALF_FOV            = CAMERA_FOV / 2.0   # 27.5 deg maps to half-frame width
SETTLE_TIME         = 0.35    # s to wait (stopped) after a turn before re-deciding
MIN_TURN_MS         = 60      # floor so tiny turns still move the motors
FIRE_LOST_GRACE     = 1.0     # s fire must stay gone before any search starts

# ── Approach tuning ───────────────────────────────────────────────────────────
STOP_DISTANCE_CM    = 20      # front distance to stop in front of the fire
APPROACH_TIMEOUT    = 8.0     # s max continuous forward without arriving (safety)

# ── Free-roam tuning ──────────────────────────────────────────────────────────

# ── Free-roam tuning ──────────────────────────────────────────────────────────
OBSTACLE_CM         = 30      # front distance that counts as a blocking obstacle
SIDE_CM             = 30      # side distance above this counts as "free" to turn
ROAM_SCAN_INTERVAL  = 10.0    # s of roaming between periodic 360 re-scans


def deviation_to_turn_ms(deviation_px, frame_half_w):
    """Pixel deviation from center → motor turn duration (ms) + angle (deg).
    Duration uses the align-speed 90° time (turns happen at SPEED_ALIGN)."""
    angle = (abs(deviation_px) / frame_half_w) * HALF_FOV
    turn_ms = (angle / 90.0) * TURN_90_ALIGN_MS
    return max(MIN_TURN_MS, turn_ms), angle


class Aligner:
    """Stateful, non-blocking align + approach decider.

    Call update() once per video frame with the current main fire target and
    the latest distance sensors. Returns the motor command to send (str) or
    None (send nothing).
    """

    IDLE      = "IDLE"
    TURNING   = "TURNING"
    SETTLING  = "SETTLING"
    APPROACH  = "APPROACH"
    ARRIVED   = "ARRIVED"
    SCANNING  = "SCANNING"     # stepped 360 sweep looking for fire
    ROAMING   = "ROAMING"      # free-roam wander with obstacle avoidance

    def __init__(self, logger=None):
        # logger(msg: str, cls: str) — optional, mirrors decisions to dashboard
        self._log = logger or (lambda msg, cls="info": None)
        self.state = self.IDLE
        self.turn_end = 0.0        # wall-clock time the current turn should stop
        self.settle_end = 0.0      # wall-clock time the settle window ends
        self.approach_start = 0.0  # wall-clock time the current approach began
        self.last_sent = None      # last command returned (avoids spam)
        # search/roam phase machinery (all wall-clock, non-blocking)
        self.scan_steps_left = 0   # scan steps remaining in the current sweep
        self.scan_phase = "turn"   # "turn" | "look" within a scan step
        self.phase_end = 0.0       # wall-clock end of the current scan/roam phase
        self.roam_phase = "drive"  # "drive" | "turn" within roaming
        self.roam_clear_start = 0.0  # when the current clear forward run began
        self.fire_lost_since = None  # wall-clock when fire was last lost (grace timer)

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

    def _go(self, state, cmd, msg, cls="info"):
        """Transition to a state, log it, and return the command to send."""
        self.state = state
        self.last_sent = cmd
        if msg:
            self._log(msg, cls)
        return cmd

    def update(self, main_target, frame_w, sensors=None, now=None):
        """Decide the next motor command.

        main_target: dict with 'deviation' (px, signed: +right/-left) or None.
        frame_w:     current frame width (px).
        sensors:     dict {left, center, right} in cm (center used for approach).
        now:         wall-clock seconds (defaults to time.time()).

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
        deviation = main_target["deviation"] if main_target else None

        # ── FIRE = HIGHEST PRIORITY — everything else is secondary ───────────
        if main_target is not None:
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

        # ── Finish an in-progress turn (non-blocking) ───────────────────────
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

        # ── APPROACH: drive forward, watch fire + front sensor ──────────────
        if self.state == self.APPROACH:
            if main_target is None:
                return self._go(self.IDLE, "STOP",
                                "✋ fire lost during approach — STOP", "warn")
            if center > 0 and center <= STOP_DISTANCE_CM:
                return self._go(self.ARRIVED, "STOP",
                                f"✅ ARRIVED — front={center}cm (≤{STOP_DISTANCE_CM}) STOP", "info")
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

        # ── ARRIVED: hold. Re-acquire only if fire lost ─────────────────────
        if self.state == self.ARRIVED:
            if main_target is None:
                return self._go(self.IDLE, "STOP", "fire lost — back to idle", "warn")
            if self.last_sent != "STOP":
                self.last_sent = "STOP"
                return "STOP"
            return None

        # ── IDLE: decide based on current target ────────────────────────────
        if main_target is None:
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
                return self._go(self.ARRIVED, "STOP",
                                f"✅ ARRIVED — front={center}cm STOP", "info")
            # Centered, not there yet → start approaching at slow align speed
            self.approach_start = now
            return self._go(self.APPROACH, _fwd(SPEED_APPROACH),
                            f"🎯 centered dev={deviation:+d}px → APPROACH (front={center}cm) @spd{SPEED_APPROACH}", "info")

        # Off-center → start a proportional turn at slow align speed
        turn_ms, angle = deviation_to_turn_ms(deviation, frame_half_w)
        cmd = _turn_l(SPEED_ALIGN) if deviation < 0 else _turn_r(SPEED_ALIGN)
        self.turn_end = now + turn_ms / 1000.0
        return self._go(self.TURNING, cmd,
                        f"↺ dev={deviation:+d}px → {angle:.1f}° {cmd} for {turn_ms:.0f}ms", "info")

    # ── SCANNING: one continuous 360° spin at scan speed ────────────────────
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

    # ── ROAMING: wander forward, avoid obstacles, periodic re-scan ──────────
    def _start_roam(self, now):
        self.roam_phase = "drive"
        self.roam_clear_start = now   # anchor for the periodic 360 re-scan
        return self._go(self.ROAMING, _fwd(SPEED_IDLE), "🚶 free-roam — drive forward", "info")

    def _roam_tick(self, now, center, left, right):
        fwd      = _fwd(SPEED_IDLE)
        turn90_s  = TURN_90_IDLE_MS  / 1000.0
        turn180_s = TURN_180_IDLE_MS / 1000.0

        # finishing an avoidance turn? → reset scan timer (target-lock priority)
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

        # 10s of uninterrupted clear driving → 360 re-scan (obstacle/fire reset it)
        if (now - self.roam_clear_start) >= ROAM_SCAN_INTERVAL:
            self._log(f"⏱ {ROAM_SCAN_INTERVAL:.0f}s clear — 360° re-scan", "info")
            return self._start_scan(now)

        # keep cruising
        if self.last_sent != fwd:
            self.last_sent = fwd
            return fwd
        return None
