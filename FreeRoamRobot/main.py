#!/usr/bin/env python3
"""
Giriş noktası — Pi üzerinde çalıştır:

  python main.py --source 0 --serial-port /dev/ttyUSB0 --no-gui
  python main.py --source 0 --no-gui           # serial olmadan (test)

Modüller:
  pi/config.py             — sabitler + log()
  pi/model_utils.py        — YOLO model indirme/önbellekleme
  pi/serial_bridge.py      — Arduino serial (send / read_arduino)
  pi/fsm.py                — free_roam + fire_mission FSM
  pi/yolo_tracker.py       — YOLO worker thread
  pi/arduino_controller.py — Arduino worker thread
"""
import argparse
import queue
import threading
from pathlib import Path

import cv2
from ultralytics import YOLO

try:
    import serial as _serial
    _SERIAL_AVAILABLE = True
except ImportError:
    _SERIAL_AVAILABLE = False

from pi.config import log, ARDUINO_IMG_WIDTH
from pi.model_utils import ensure_local_model
from pi.yolo_tracker import yolo_worker
from pi.arduino_controller import arduino_worker

DEFAULT_HF_REPO     = "SalahALHaismawi/yolov26-fire-detection"
DEFAULT_HF_FILE     = "best.pt"
DEFAULT_LOCAL_MODEL = Path(__file__).resolve().parent / "models" / "best.pt"


def parse_args():
    p = argparse.ArgumentParser(description="Fire/Smoke detection — threaded")
    p.add_argument("--hf-repo",        default=DEFAULT_HF_REPO)
    p.add_argument("--hf-file",        default=DEFAULT_HF_FILE)
    p.add_argument("--hf-cache-dir",   default=str(Path.home() / ".cache" / "fire-smoke-models"))
    p.add_argument("--model-path",     default=str(DEFAULT_LOCAL_MODEL))
    p.add_argument("--source",         default="0", help="Kamera index veya video yolu")
    p.add_argument("--conf",           type=float, default=0.60)
    p.add_argument("--target-classes", default="fire")
    p.add_argument("--alert-hold",     type=float, default=2.0,
                   help="Nesne bu süre görünürse alert tetiklenir (sn)")
    p.add_argument("--save",           action="store_true", help="Çıktı videosunu kaydet")
    p.add_argument("--no-gui",         action="store_true", help="GUI'yi kapat (headless)")
    p.add_argument("--output",         default="alert_output.mp4")
    p.add_argument("--serial-port",    default=None,
                   help="Arduino portu: /dev/ttyUSB0 veya /dev/ttyAMA0")
    p.add_argument("--serial-baud",    type=int, default=115200)
    return p.parse_args()


def main():
    args = parse_args()
    log(f"[INFO] source={args.source} conf={args.conf} "
        f"alert_hold={args.alert_hold} no_gui={args.no_gui} save={args.save}")

    # Model hazırla
    local_model_path = Path(args.model_path).expanduser().resolve()
    try:
        model_path = ensure_local_model(
            args.hf_repo, args.hf_file, args.hf_cache_dir, local_model_path
        )
    except Exception as exc:
        log(f"[ERROR] Model hazırlanamadı: {exc}")
        raise

    target_classes = {c.strip().lower() for c in args.target_classes.split(",") if c.strip()}
    if not target_classes:
        raise ValueError("En az bir hedef sınıf gerekli (--target-classes fire)")

    model = YOLO(str(model_path))
    log(f"[INFO] YOLO yüklendi: {model_path}")

    # Kamera
    src = int(args.source) if args.source.isdigit() else args.source
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        raise RuntimeError(f"Kamera açılamadı: {args.source}")
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or ARDUINO_IMG_WIDTH
    log(f"[INFO] Kamera: {args.source}  genişlik={frame_width}px")

    # Video kaydedici (opsiyonel)
    writer = None
    if args.save:
        w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25
        writer = cv2.VideoWriter(
            args.output, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h)
        )
        log(f"[INFO] Video kaydedici: {args.output} {w}x{h}@{fps:.0f}fps")

    # Serial (opsiyonel)
    ser = None
    if args.serial_port:
        if not _SERIAL_AVAILABLE:
            raise RuntimeError("pyserial kurulu değil: pip install pyserial")
        # timeout=0.05 → readline Arduino thread'ini bloklamasın
        ser = _serial.Serial(args.serial_port, args.serial_baud, timeout=0.05)
        log(f"[SERIAL] {args.serial_port} @ {args.serial_baud} baud")
    else:
        log("[SERIAL] --serial-port verilmedi. Serial devre dışı.")

    # Paylaşılan durum
    shared_tracks = {}
    tracks_lock   = threading.Lock()
    stop_event    = threading.Event()
    frame_q       = queue.Queue(maxsize=2)

    # YOLO thread
    yolo_t = threading.Thread(
        target=yolo_worker,
        args=(cap, model, args, target_classes,
              shared_tracks, tracks_lock, stop_event, frame_q, writer),
        daemon=True, name="yolo",
    )
    yolo_t.start()
    log("[INFO] YOLO thread başlatıldı.")

    # Arduino thread (serial varsa)
    arduino_t = None
    if ser:
        arduino_t = threading.Thread(
            target=arduino_worker,
            args=(ser, frame_width, shared_tracks, tracks_lock, stop_event),
            daemon=True, name="arduino",
        )
        arduino_t.start()
        log("[INFO] Arduino thread başlatıldı.")

    # Ana thread: GUI (cv2.imshow macOS'ta main thread'de olmak zorunda)
    show_gui = not args.no_gui
    log("[INFO] GUI aktif — 'q' ile çık." if show_gui else "[INFO] GUI kapalı — Ctrl+C.")

    try:
        while not stop_event.is_set():
            try:
                frame = frame_q.get(timeout=0.1)
            except queue.Empty:
                frame = None

            if frame is not None and show_gui:
                cv2.imshow("Fire/Smoke Detection", frame)

            if show_gui and (cv2.waitKey(1) & 0xFF == ord("q")):
                log("[INFO] 'q' basıldı.")
                stop_event.set()
                break
    except KeyboardInterrupt:
        log("[INFO] Ctrl+C alındı.")
        stop_event.set()

    # Temizlik
    yolo_t.join(timeout=3)
    if arduino_t:
        arduino_t.join(timeout=3)
    cap.release()
    if writer:
        writer.release()
    if ser:
        ser.close()
        log("[SERIAL] Port kapatıldı.")
    cv2.destroyAllWindows()
    log("[INFO] Çıkış tamamlandı.")


if __name__ == "__main__":
    main()
