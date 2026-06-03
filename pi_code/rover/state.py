#!/usr/bin/env python3
"""Thread-safe shared state between the rover's background threads.

One small store with one lock, replacing the scattered module-level globals.
Producers (serial reader, video pipeline) write; consumers (web routes, MJPEG
stream, autonomy) read. All access goes through these methods.
"""

from __future__ import annotations

import threading

from rover.protocol import SensorData, NO_SENSOR_DATA


class SharedState:
    def __init__(self):
        self._lock = threading.Lock()
        self._sensors: SensorData = NO_SENSOR_DATA
        self._frame: bytes | None = None          # latest annotated JPEG
        self._fire: dict = {"detected": False, "count": 0}

    # ── Sensors (written by the serial reader) ───────────────────────────────
    def set_sensors(self, data: SensorData) -> None:
        with self._lock:
            self._sensors = data

    def get_sensors(self) -> SensorData:
        with self._lock:
            return self._sensors

    # ── Video frame (written by the vision pipeline) ─────────────────────────
    def set_frame(self, jpeg: bytes) -> None:
        with self._lock:
            self._frame = jpeg

    def get_frame(self) -> bytes | None:
        with self._lock:
            return self._frame

    # ── Fire status (written by the vision pipeline) ─────────────────────────
    def set_fire(self, payload: dict) -> None:
        with self._lock:
            self._fire = payload

    def get_fire(self) -> dict:
        with self._lock:
            return dict(self._fire)
