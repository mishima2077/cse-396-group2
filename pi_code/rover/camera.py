#!/usr/bin/env python3
"""Camera discovery + capture wrapper.

Thin layer over cv2.VideoCapture: find a working index, request max resolution
(the driver clamps to the sensor max), warm up, then read frames.
"""

from __future__ import annotations

import time
from typing import Callable

import cv2

LogFn = Callable[[str, str], None]


def find_camera(max_index: int = 5, on_log: LogFn | None = None) -> int:
    log = on_log or (lambda msg, cls="info": None)
    for i in range(max_index):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            cap.release()
            log(f"[CAM] Found camera {i}")
            return i
    return 0


class Camera:
    def __init__(self, index: int, on_log: LogFn | None = None):
        self.index = index
        self._log = on_log or (lambda msg, cls="info": None)
        self.cap: cv2.VideoCapture | None = None
        self.width = 0
        self.height = 0

    def open(self) -> bool:
        cap = cv2.VideoCapture(self.index)
        # Request max resolution — driver clamps the oversized request to sensor max
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 10000)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 10000)
        cap.set(cv2.CAP_PROP_FPS, 30)
        self.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._log(f"[CAM] Resolution {self.width}x{self.height} @ {cap.get(cv2.CAP_PROP_FPS):.0f}fps")

        # warm-up — let auto-exposure/gain settle before streaming
        for _ in range(5):
            cap.read()
            time.sleep(0.1)

        self.cap = cap
        if cap.isOpened():
            self._log(f"[CAM] Streaming camera {self.index}")
            return True
        self._log("[CAM] Could not open camera", "warn")
        return False

    def read(self):
        return self.cap.read()

    def release(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self._log("[CAM] Camera released")
