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

# ── Motor speed ───────────────────────────────────────────────────────────────
# New Arduino interface: motion commands are "CMD,SPEED" (speed 0-255).
# For now every autonomous motion runs at full speed; later this becomes
# dynamic (e.g. slow down near the fire / based on confidence).
MAX_SPEED = 255

# Pre-built motion command strings (STOP takes no speed argument).
FWD    = f"FWD,{MAX_SPEED}"
TURN_L = f"TURN_L,{MAX_SPEED}"
TURN_R = f"TURN_R,{MAX_SPEED}"

# ── Alignment tuning ──────────────────────────────────────────────────────────
ALIGNMENT_THRESHOLD = 40      # px from center counted as "centered" (dead zone)
REALIGN_THRESHOLD   = 80      # px drift during approach before re-centering
TURN_90_MS          = 1200    # ms of motor turn = 90 degrees (measured)
CAMERA_FOV          = 55      # camera horizontal field of view (degrees)
HALF_FOV            = CAMERA_FOV / 2.0   # 27.5 deg maps to half-frame width
SETTLE_TIME         = 0.35    # s to wait (stopped) after a turn before re-deciding
MIN_TURN_MS         = 60      # floor so tiny turns still move the motors
FIRE_LOST_GRACE     = 1.0     # s fire must stay gone before any search starts

# ── Approach tuning ───────────────────────────────────────────────────────────
STOP_DISTANCE_CM    = 20      # front distance to stop in front of the fire
APPROACH_TIMEOUT    = 8.0     # s max continuous forward without arriving (safety)

# ── Search / scan tuning ──────────────────────────────────────────────────────
SCAN_STEP_MS        = TURN_90_MS / 3.0   # ms of turn = 30 deg (one scan step)
SCAN_SETTLE         = 0.4     # s stopped at each step so YOLO gets a clean look
SCAN_STEPS_FULL     = 12      # 12 x 30 = 360 deg full sweep
SCAN_STEP_DEG       = 360 // SCAN_STEPS_FULL
TURN_180_MS         = TURN_90_MS * 2.0   # ms of turn = 180 deg (roam u-turn)

# ── Free-roam tuning ──────────────────────────────────────────────────────────
OBSTACLE_CM         = 30      # front distance that counts as a blocking obstacle
SIDE_CM             = 30      # side distance above this counts as "free" to turn
ROAM_SCAN_INTERVAL  = 10.0    # s of roaming between periodic 360 re-scans


def deviation_to_turn_ms(deviation_px, frame_half_w):
    """Pixel deviation from center → motor turn duration (ms) + angle (deg)."""
    angle = (abs(deviation_px) / frame_half_w) * HALF_FOV
    turn_ms = (angle / 90.0) * TURN_90_MS
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
            # keep driving forward (send FWD once, then nothing)
            if self.last_sent != FWD:
                self.last_sent = FWD
                return FWD
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
            # Centered, not there yet → start approaching
            self.approach_start = now
            return self._go(self.APPROACH, FWD,
                            f"🎯 centered dev={deviation:+d}px → APPROACH (front={center}cm) FWD", "info")

        # Off-center → start a proportional turn
        turn_ms, angle = deviation_to_turn_ms(deviation, frame_half_w)
        cmd = TURN_L if deviation < 0 else TURN_R
        self.turn_end = now + turn_ms / 1000.0
        return self._go(self.TURNING, cmd,
                        f"↺ dev={deviation:+d}px → {angle:.1f}° {cmd} for {turn_ms:.0f}ms", "info")

    # ── SCANNING: stepped 360 sweep, stop-and-look each step ────────────────
    def _start_scan(self, now):
        """Begin a fresh stepped sweep (8 x 45 deg, look between each step)."""
        self.scan_steps_left = SCAN_STEPS_FULL
        self.scan_phase = "turn"
        self.phase_end = now + SCAN_STEP_MS / 1000.0
        return self._go(self.SCANNING, TURN_R,
                        f"🔍 scan start — {SCAN_STEPS_FULL}×{SCAN_STEP_DEG}° sweep", "info")

    def _scan_tick(self, now):
        """Advance the sweep. Fire (if any) is caught by preemption upstream."""
        if self.scan_phase == "turn":
            if now >= self.phase_end:
                self.scan_phase = "look"           # stop and let YOLO look
                self.phase_end = now + SCAN_SETTLE
                self.last_sent = "STOP"
                return "STOP"
            return None                            # still turning this step
        # look phase — standing still; no fire (else preempted)
        if now < self.phase_end:
            return None
        self.scan_steps_left -= 1
        if self.scan_steps_left <= 0:
            return self._start_roam(now)           # full sweep, nothing → roam
        self.scan_phase = "turn"
        self.phase_end = now + SCAN_STEP_MS / 1000.0
        self.last_sent = TURN_R
        return TURN_R

    # ── ROAMING: wander forward, avoid obstacles, periodic re-scan ──────────
    def _start_roam(self, now):
        self.roam_phase = "drive"
        self.roam_clear_start = now   # anchor for the periodic 360 re-scan
        return self._go(self.ROAMING, FWD, "🚶 free-roam — drive forward", "info")

    def _roam_tick(self, now, center, left, right):
        # finishing an avoidance turn? → reset scan timer (target-lock priority)
        if self.roam_phase == "turn":
            if now >= self.phase_end:
                self.roam_phase = "drive"
                self.roam_clear_start = now        # avoidance resets the 10s timer
                self.last_sent = FWD
                return FWD
            return None                            # still turning

        # driving forward — obstacle ahead? (0 = no echo = clear)
        if 0 < center <= OBSTACLE_CM:
            right_free = (right == 0) or (right > SIDE_CM)
            left_free  = (left == 0)  or (left > SIDE_CM)
            if right_free:
                self.roam_phase = "turn"
                self.phase_end = now + TURN_90_MS / 1000.0
                return self._go(self.ROAMING, TURN_R,
                                f"⛔ front={center}cm → right free → 90° TURN_R", "warn")
            if left_free:
                self.roam_phase = "turn"
                self.phase_end = now + TURN_90_MS / 1000.0
                return self._go(self.ROAMING, TURN_L,
                                f"⛔ front={center}cm → left free → 90° TURN_L", "warn")
            self.roam_phase = "turn"
            self.phase_end = now + TURN_180_MS / 1000.0
            return self._go(self.ROAMING, TURN_R,
                            f"⛔ front={center}cm boxed in → 180° U-turn", "warn")

        # 10s of uninterrupted clear driving → 360 re-scan (obstacle/fire reset it)
        if (now - self.roam_clear_start) >= ROAM_SCAN_INTERVAL:
            self._log(f"⏱ {ROAM_SCAN_INTERVAL:.0f}s clear — 360° re-scan", "info")
            return self._start_scan(now)

        # keep cruising
        if self.last_sent != FWD:
            self.last_sent = FWD
            return FWD
        return None
