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
MAX_SPEED = 255

# ── Alignment tuning ──────────────────────────────────────────────────────────
ALIGNMENT_THRESHOLD = 40      # px from center counted as "centered" (dead zone)
REALIGN_THRESHOLD   = 80      # px drift during approach before re-centering
TURN_90_MS          = 1200    # ms of motor turn = 90 degrees (measured)
CAMERA_FOV          = 55      # camera horizontal field of view (degrees)
HALF_FOV            = CAMERA_FOV / 2.0   # 27.5 deg maps to half-frame width
SETTLE_TIME         = 0.35    # s to wait (stopped) after a turn before re-deciding
MIN_TURN_MS         = 60      # floor so tiny turns still move the motors

# ── Approach tuning ───────────────────────────────────────────────────────────
STOP_DISTANCE_CM    = 20      # front distance to stop in front of the fire
APPROACH_TIMEOUT    = 8.0     # s max continuous forward without arriving (safety)


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

    def __init__(self, logger=None):
        # logger(msg: str, cls: str) — optional, mirrors decisions to dashboard
        self._log = logger or (lambda msg, cls="info": None)
        self.state = self.IDLE
        self.turn_end = 0.0        # wall-clock time the current turn should stop
        self.settle_end = 0.0      # wall-clock time the settle window ends
        self.approach_start = 0.0  # wall-clock time the current approach began
        self.last_sent = None      # last command returned (avoids spam)

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
        deviation = main_target["deviation"] if main_target else None

        # ── Finish an in-progress turn (non-blocking) ───────────────────────
        if self.state == self.TURNING:
            if now >= self.turn_end:
                self.state = self.SETTLING
                self.settle_end = now + SETTLE_TIME
                self.last_sent = f"STOP"
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
            fwd_cmd = f"FWD,{MAX_SPEED}"
            if self.last_sent != fwd_cmd:
                self.last_sent = fwd_cmd
                return fwd_cmd
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
            # hold still when no fire visible (no search yet)
            if self.last_sent != "STOP":
                self.last_sent = "STOP"
                return "STOP"
            return None

        if abs(deviation) <= ALIGNMENT_THRESHOLD:
            # Centered — already at the fire?
            if center > 0 and center <= STOP_DISTANCE_CM:
                return self._go(self.ARRIVED, "STOP",
                                f"✅ ARRIVED — front={center}cm STOP", "info")
            # Centered, not there yet → start approaching
            self.approach_start = now
            fwd_cmd = f"FWD,{MAX_SPEED}"
            return self._go(self.APPROACH, fwd_cmd,
                            f"🎯 centered dev={deviation:+d}px → APPROACH (front={center}cm) FWD", "info")

        # Off-center → start a proportional turn
        turn_ms, angle = deviation_to_turn_ms(deviation, frame_half_w)
        turn_dir = "TURN_L" if deviation < 0 else "TURN_R"
        cmd = f"{turn_dir},{MAX_SPEED}"
        self.turn_end = now + turn_ms / 1000.0
        return self._go(self.TURNING, cmd,
                        f"↺ dev={deviation:+d}px → {angle:.1f}° {turn_dir} for {turn_ms:.0f}ms", "info")
