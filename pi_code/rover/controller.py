#!/usr/bin/env python3
"""RoverController — owns the serial link, the autonomy FSM, and the mode flag.

This is the single place that decides *who is allowed to drive*:
  • AUTO   → the autonomy FSM issues commands each frame; manual input ignored.
  • MANUAL → the FSM is paused; only dashboard commands move the rover.

The video loop calls ``on_frame`` every frame; the web layer calls
``manual_command`` and ``set_mode``. Neither needs to know the rule — it lives
here.
"""

from __future__ import annotations

import threading
import time
from typing import Callable

from rover import protocol
from rover.autonomy import Aligner
from rover.config import RoverConfig

LogFn = Callable[[str, str], None]
ModeFn = Callable[[bool], None]


class RoverController:
    def __init__(self, serial_link, cfg: RoverConfig,
                 on_log: LogFn | None = None, on_mode: ModeFn | None = None,
                 autonomy_enabled: bool = True):
        self.serial = serial_link
        self.cfg = cfg
        self._log = on_log or (lambda msg, cls="info": None)
        self._on_mode = on_mode or (lambda manual: None)
        self.autonomy_enabled = autonomy_enabled
        self.aligner = Aligner(logger=on_log)
        self._manual = True          # boot in manual — operator drives until AUTO chosen
        self._lock = threading.Lock()

    @property
    def is_manual(self) -> bool:
        with self._lock:
            return self._manual

    def set_mode(self, manual: bool) -> None:
        """Switch manual/auto. Always stops the rover; resets the FSM on → auto."""
        manual = bool(manual)
        with self._lock:
            self._manual = manual
        self.send(protocol.STOP)
        self.send("PUMP_OFF")        # never leave the pump running across a mode switch
        if manual:
            self._log("⚙ MANUAL mode — FSM paused, dashboard in control", "warn")
        else:
            self.aligner.reset()
            self._log("⚙ AUTO mode — FSM active, dashboard locked", "info")
        self._on_mode(manual)

    def send(self, cmd: str) -> bool:
        """Send a raw command to the Arduino and mirror it to the log."""
        ok = self.serial.send(cmd)
        if ok:
            self._log(f"➤ SERIAL → {cmd}", "cmd")
        return ok

    def on_frame(self, deviation, frame_w, sensors, now=None) -> None:
        """Per-frame autonomy tick. No-op in manual mode or when autonomy is off."""
        if self._manual or not self.autonomy_enabled:
            return
        cmd = self.aligner.update(deviation, frame_w, sensors, now or time.time())
        if cmd is not None:
            self.send(cmd)

    def manual_command(self, cmd: str, speed=None) -> bool:
        """Dashboard motion/pump command. Honored only in manual mode."""
        if not self.is_manual:
            return False
        cmd = cmd.strip().upper()
        if cmd in protocol.MOTION_CMDS:
            spd = speed if speed is not None else self.cfg.server.max_speed
            return self.send(protocol.motion(cmd, spd))
        if cmd in protocol.SIMPLE_CMDS:
            return self.send(cmd)
        self._log(f"Unknown command: {cmd}", "warn")
        return False
