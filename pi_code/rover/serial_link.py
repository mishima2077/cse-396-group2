#!/usr/bin/env python3
"""Arduino serial I/O — port discovery, connect, send, and the read loop.

Knows nothing about the web layer. All human-readable output goes through the
injected ``on_log(msg, cls)`` callback, so this module is usable (and testable)
without Flask.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

import serial

from rover.config import SerialCfg
from rover.protocol import parse_sensor_frame

LogFn = Callable[[str, str], None]


class SerialLink:
    def __init__(self, cfg: SerialCfg, on_log: LogFn | None = None):
        self.cfg = cfg
        self._log = on_log or (lambda msg, cls="info": None)
        self._serial: serial.Serial | None = None
        self._lock = threading.Lock()

    @property
    def connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def find_port(self) -> str | None:
        for port in self.cfg.ports:
            if Path(port).exists():
                self._log(f"[SERIAL] Auto-detected {port}")
                return port
        return None

    def connect(self, port: str | None = None) -> bool:
        """Open the given port (or auto-detect). Returns True on success."""
        port = port or self.find_port()
        if not port:
            self._log("[SERIAL] No port found — running without Arduino", "warn")
            return False
        try:
            self._serial = serial.Serial(port, self.cfg.baud, timeout=self.cfg.timeout_s)
            self._log(f"[SERIAL] Connected {port} @ {self.cfg.baud}")
            return True
        except serial.SerialException as e:
            self._log(f"[SERIAL] Not connected ({e}). Sensor data will be empty.", "warn")
            self._serial = None
            return False

    def send(self, cmd: str) -> bool:
        """Write one command line to the Arduino. Returns True if it went out."""
        with self._lock:
            if not self.connected:
                self._log(f"⚠ no serial — dropped: {cmd}", "warn")
                return False
            try:
                self._serial.write((cmd + "\n").encode())
                self._serial.flush()
                return True
            except Exception as e:
                self._log(f"✗ SERIAL write error: {e}", "warn")
                return False

    def read_loop(self, state, on_sensor, stop, emit_hz: int) -> None:
        """Read telemetry lines forever (until ``stop()`` is True).

        Every parsed frame updates ``state``; ``on_sensor(dict)`` is called at
        most ``emit_hz`` times per second (the dashboard push throttle).
        """
        min_interval = 1.0 / emit_hz
        last_emit = 0.0
        while not stop():
            if not self.connected:
                time.sleep(0.5)
                continue
            try:
                if self._serial.in_waiting:
                    line = self._serial.readline().decode(errors="replace").strip()
                    frame = parse_sensor_frame(line)
                    if frame is not None:
                        state.set_sensors(frame)
                        now = time.time()
                        if now - last_emit >= min_interval:
                            on_sensor(frame.as_dict())
                            last_emit = now
                else:
                    time.sleep(0.005)
            except Exception as e:
                self._log(f"[SERIAL] Read error: {e}", "warn")
                time.sleep(0.2)

    def close(self) -> None:
        with self._lock:
            if self.connected:
                self._serial.close()
