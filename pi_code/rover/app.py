#!/usr/bin/env python3
"""Entry point / orchestration — wires everything together and runs.

Builds the config, shared state, serial link, vision pipeline, controller, and
web server; starts the background threads; then runs the SocketIO server.

Usage:
    python3 run.py
    python3 run.py --port 5001 --no-yolo
    python3 run.py --serial /dev/ttyACM0 --no-align
"""

from __future__ import annotations

import argparse
import threading
import time

import cv2

from rover import vision, web
from rover.camera import Camera, find_camera
from rover.config import CONFIG
from rover.controller import RoverController
from rover.serial_link import SerialLink
from rover.state import SharedState
from rover.vision import FireDetector


def parse_args():
    p = argparse.ArgumentParser(description="Rover dashboard server")
    p.add_argument("--host",   default=CONFIG.server.host)
    p.add_argument("--port",   type=int, default=CONFIG.server.port)
    p.add_argument("--serial", default=None, help="Serial port (default: auto-detect)")
    p.add_argument("--baud",   type=int, default=CONFIG.serial.baud)
    p.add_argument("--camera", type=int, default=None)
    p.add_argument("--no-yolo", action="store_true", help="Disable YOLO inference")
    p.add_argument("--no-align", action="store_true",
                   help="Disable autonomous alignment (observe only, no motor commands)")
    return p.parse_args()


def video_loop(camera, detector, state, controller, on_log, on_fire, stop):
    """Capture → detect → annotate → autonomy → encode → publish, per frame."""
    if not camera.open():
        return

    encode_params = [cv2.IMWRITE_JPEG_QUALITY, CONFIG.vision.mjpeg_quality]
    last_fire_emit = 0.0
    prev_detected = False

    while not stop():
        ok, frame = camera.read()
        if not ok:
            time.sleep(0.05)
            continue

        h, w = frame.shape[:2]
        targets = detector.detect(frame)
        vision.annotate(frame, targets)
        target = vision.main_target(targets)

        # ── Autonomy (auto mode only — controller enforces the rule) ─────────
        deviation = target.deviation if target else None
        sensors = state.get_sensors().as_dict()
        controller.on_frame(deviation, w, sensors)

        # ── Fire status: publish to state + dashboard (rate-limited) ─────────
        now = time.time()
        payload = {
            "detected": bool(targets),
            "count": len(targets),
            "cx": target.cx if target else None,
            "cy": target.cy if target else None,
            "deviation": target.deviation if target else None,
            "conf": target.conf if target else None,
            "frame_w": w, "frame_h": h,
        }
        state.set_fire(payload)
        changed = prev_detected != payload["detected"]
        prev_detected = payload["detected"]
        if changed or (now - last_fire_emit) >= 0.2:
            on_fire(payload)
            last_fire_emit = now
        if changed:
            if payload["detected"]:
                on_log(f"🔥 FIRE DETECTED — cx={payload['cx']} dev={payload['deviation']}px "
                       f"conf={payload['conf']}", "fire")
            else:
                on_log("Fire lost — no detection", "warn")

        # Overlay timestamp, then encode for the MJPEG stream
        cv2.putText(frame, time.strftime("%H:%M:%S"),
                    (10, frame.shape[0] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        ok2, jpeg = cv2.imencode(".jpg", frame, encode_params)
        if ok2:
            state.set_frame(jpeg.tobytes())

    camera.release()


def main():
    args = parse_args()

    state = SharedState()
    app, socketio = web.create_app(state)

    # One logger: console (always) + dashboard (broadcast). Every module logs here.
    def on_log(msg, cls="info"):
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)
        socketio.emit("log", {"msg": msg, "cls": cls})

    stop_event = threading.Event()

    # ── Serial link ─────────────────────────────────────────────────────────
    serial_link = SerialLink(CONFIG.serial, on_log=on_log)
    serial_link.connect(args.serial)

    # ── Controller (mode policy + autonomy) ─────────────────────────────────
    controller = RoverController(
        serial_link, CONFIG, on_log=on_log,
        on_mode=lambda manual: socketio.emit("mode_changed", {"manual": manual}),
        autonomy_enabled=not args.no_align,
    )
    web.register_socket_handlers(socketio, controller)
    if args.no_align:
        on_log("[ALIGN] Disabled (observe only — no motor commands)")
    else:
        on_log("[ALIGN] Autonomous alignment ENABLED")

    # ── Vision detector ─────────────────────────────────────────────────────
    detector = FireDetector(CONFIG.vision, on_log=on_log)
    if args.no_yolo:
        on_log("[YOLO] Disabled")
    else:
        detector.load()

    # ── Background threads ──────────────────────────────────────────────────
    threading.Thread(
        target=serial_link.read_loop,
        args=(state, lambda d: socketio.emit("sensor", d),
              stop_event.is_set, CONFIG.server.sensor_emit_hz),
        daemon=True,
    ).start()

    cam_idx = args.camera if args.camera is not None else find_camera(on_log=on_log)
    camera = Camera(cam_idx, on_log=on_log)
    threading.Thread(
        target=video_loop,
        args=(camera, detector, state, controller, on_log,
              lambda p: socketio.emit("fire_yolo", p), stop_event.is_set),
        daemon=True,
    ).start()

    on_log(f"[SERVER] Dashboard at http://{args.host}:{args.port}")
    on_log(f"[SERVER] PC'den erişim: http://<pi-ip>:{args.port}")

    try:
        socketio.run(app, host=args.host, port=args.port, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        if serial_link.connected:
            controller.send("STOP")
            serial_link.close()
        on_log("[SERVER] Stopped")


if __name__ == "__main__":
    main()
