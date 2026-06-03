#!/usr/bin/env python3
"""YOLO fire detection + frame annotation.

``FireDetector`` wraps the YOLO model and the every-Nth-frame inference skip
(reusing the cached result between runs). It produces ``FireTarget`` records;
``annotate`` draws them. No camera, no serial, no web here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2

from rover.config import VisionCfg

LogFn = Callable[[str, str], None]


@dataclass
class FireTarget:
    x1: int
    y1: int
    x2: int
    y2: int
    cx: int
    cy: int
    conf: float
    label: str
    deviation: int      # signed px from frame center: +right / -left


def ensure_model(cfg: VisionCfg, on_log: LogFn | None = None) -> Path:
    """Return the local model path, downloading it once from HF if missing."""
    log = on_log or (lambda msg, cls="info": None)
    if cfg.model_path.exists():
        log(f"[YOLO] Using existing model: {cfg.model_path}")
        return cfg.model_path
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        raise RuntimeError("huggingface_hub not installed: pip install huggingface_hub")
    cfg.model_path.parent.mkdir(parents=True, exist_ok=True)
    log("[YOLO] Downloading model from HuggingFace (one-time)...")
    downloaded = hf_hub_download(
        repo_id=cfg.hf_repo,
        filename=cfg.hf_file,
        cache_dir=str(Path.home() / ".cache" / "fire-models"),
    )
    import shutil
    shutil.copy2(downloaded, cfg.model_path)
    log(f"[YOLO] Model saved to: {cfg.model_path}")
    return cfg.model_path


class FireDetector:
    """YOLO fire detector with built-in frame-skip caching."""

    def __init__(self, cfg: VisionCfg, on_log: LogFn | None = None):
        self.cfg = cfg
        self._log = on_log or (lambda msg, cls="info": None)
        self._model = None
        self._frame_n = 0
        self._cache: list[FireTarget] = []

    @property
    def enabled(self) -> bool:
        return self._model is not None

    def load(self) -> bool:
        """Load the YOLO model. Returns True on success (else detect() is a no-op)."""
        try:
            model_path = ensure_model(self.cfg, self._log)
            from ultralytics import YOLO
            self._model = YOLO(str(model_path))
            self._log(f"[YOLO] Model loaded: {model_path}")
            return True
        except Exception as e:
            self._log(f"[YOLO] Failed to load model: {e}. Continuing without YOLO.", "warn")
            self._model = None
            return False

    def detect(self, frame) -> list[FireTarget]:
        """Fire targets for this frame.

        Runs YOLO only every ``cfg.every_n`` frames; returns the cached result
        on the in-between frames so boxes still draw on every frame.
        """
        self._frame_n += 1
        if self._model is None:
            return []
        if self._frame_n % self.cfg.every_n != 0:
            return self._cache

        half_w = frame.shape[1] // 2
        targets: list[FireTarget] = []
        results = self._model.predict(source=frame, conf=self.cfg.conf,
                                      imgsz=self.cfg.imgsz, verbose=False)
        for r in results:
            if r.boxes is None:
                continue
            for b in r.boxes:
                label = str(r.names.get(int(b.cls[0].item()), "?")).lower()
                if label not in self.cfg.labels:
                    continue   # ignore non-fire objects entirely
                x1, y1, x2, y2 = map(int, b.xyxy[0].tolist())
                conf = float(b.conf[0].item())
                cx = (x1 + x2) // 2
                cy = (y1 + y2) // 2
                targets.append(FireTarget(
                    x1=x1, y1=y1, x2=x2, y2=y2, cx=cx, cy=cy,
                    conf=round(conf, 2), label=label, deviation=cx - half_w,
                ))
        self._cache = targets
        return targets


def annotate(frame, targets: list[FireTarget], color=(0, 0, 255)) -> None:
    """Draw bounding boxes + labels for each target onto the frame (in place)."""
    for t in targets:
        cv2.rectangle(frame, (t.x1, t.y1), (t.x2, t.y2), color, 2)
        cv2.putText(frame, f"{t.label} {t.conf:.2f}",
                    (t.x1, max(20, t.y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)


def main_target(targets: list[FireTarget]) -> FireTarget | None:
    """The highest-confidence target, or None."""
    return max(targets, key=lambda t: t.conf) if targets else None
