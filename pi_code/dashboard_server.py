#!/usr/bin/env python3
"""
Rover Dashboard Server - Raspberry Pi side.

Streams YOLO-annotated video (MJPEG) and sensor data (WebSocket) to browser.
Browser sends motor commands back via WebSocket.

Requirements:
    pip install flask flask-socketio ultralytics opencv-python pyserial

Usage:
    python3 dashboard_server.py
    python3 dashboard_server.py --port 5001 --no-yolo
    python3 dashboard_server.py --serial /dev/ttyACM0
"""

import argparse
import threading
import time
import sys
import cv2
import serial
from pathlib import Path
from flask import Flask, Response, render_template
from flask_socketio import SocketIO

import align_logic

DEFAULT_MODEL  = Path(__file__).resolve().parent / "models" / "best.pt"
HF_REPO        = "SalahALHaismawi/yolov26-fire-detection"
HF_FILE        = "best.pt"
ARDUINO_PORT   = "/dev/ttyUSB0"
ARDUINO_BAUD   = 115200
YOLO_CONF      = 0.60
FIRE_LABELS    = {"fire"}   # only these labels are tracked/aligned (ignore others)
YOLO_IMGSZ     = 256  # 256 = faster than 320, still detects fire fine
YOLO_EVERY_N   = 5    # run YOLO only on every Nth frame, reuse last result
MJPEG_QUALITY  = 55   # JPEG encode quality
SENSOR_EMIT_HZ = 10   # max socket emits per second for sensor data

app = Flask(__name__)
app.config["SECRET_KEY"] = "rover-dash"
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

# ── Shared state ──────────────────────────────────────────────────────────────
_frame_lock   = threading.Lock()
_latest_frame = None          # JPEG bytes of most recent annotated frame

_sensor_lock    = threading.Lock()
_latest_sensors = {
    "left": 0, "center": 0, "right": 0,
    "flame_a": 0, "flame_d": 1,
}

_serial: serial.Serial | None = None
_serial_lock = threading.Lock()
_running = True

_yolo_fire_lock = threading.Lock()
_yolo_fire = {"detected": False, "count": 0}  # updated by video_thread
# ─────────────────────────────────────────────────────────────────────────────


def log(msg: str):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _ensure_model(local_path: Path) -> Path:
    if local_path.exists():
        log(f"[YOLO] Using existing model: {local_path}")
        return local_path
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        raise RuntimeError("huggingface_hub not installed: pip install huggingface_hub")
    local_path.parent.mkdir(parents=True, exist_ok=True)
    log("[YOLO] Downloading model from HuggingFace (one-time)...")
    downloaded = hf_hub_download(
        repo_id=HF_REPO,
        filename=HF_FILE,
        cache_dir=str(Path.home() / ".cache" / "fire-models"),
    )
    import shutil
    shutil.copy2(downloaded, local_path)
    log(f"[YOLO] Model saved to: {local_path}")
    return local_path


# ── Serial helpers ────────────────────────────────────────────────────────────

def serial_connect(port: str, baud: int) -> serial.Serial | None:
    try:
        s = serial.Serial(port, baud, timeout=1)
        log(f"[SERIAL] Connected {port} @ {baud}")
        return s
    except serial.SerialException as e:
        log(f"[SERIAL] Not connected ({e}). Sensor data will be empty.")
        return None


def send_command(cmd: str):
    """Write command to Arduino and mirror it to the dashboard log bar.

    Central choke-point: every serial byte sent to Arduino is logged here,
    so the alignment algorithm's behaviour is observable from the UI.
    """
    with _serial_lock:
        if _serial and _serial.is_open:
            try:
                _serial.write((cmd + "\n").encode())
                _serial.flush()
                log(f"[CMD] -> {cmd}")
                socketio.emit("log", {"msg": f"➤ SERIAL → {cmd}", "cls": "cmd"})
            except Exception as e:
                log(f"[CMD] Write error: {e}")
                socketio.emit("log", {"msg": f"✗ SERIAL write error: {e}", "cls": "warn"})
        else:
            log(f"[CMD] -> {cmd} (no serial)")
            socketio.emit("log", {"msg": f"⚠ no serial — dropped: {cmd}", "cls": "warn"})


def serial_reader_thread():
    """Read Arduino sensor lines, update shared state, emit via socketio."""
    global _latest_sensors
    min_interval = 1.0 / SENSOR_EMIT_HZ
    last_emit = 0.0

    while _running:
        if _serial is None:
            time.sleep(0.5)
            continue
        try:
            if _serial.in_waiting:
                line = _serial.readline().decode(errors="replace").strip()
                if line.startswith("D,"):
                    parts = line.split(",")
                    if len(parts) == 6:
                        data = {
                            "left":    int(parts[1]),
                            "center":  int(parts[2]),
                            "right":   int(parts[3]),
                            "flame_a": int(parts[4]),
                            "flame_d": int(parts[5]),
                        }
                        with _sensor_lock:
                            _latest_sensors = data

                        now = time.time()
                        if now - last_emit >= min_interval:
                            socketio.emit("sensor", data)
                            last_emit = now
            else:
                time.sleep(0.005)
        except Exception as e:
            log(f"[SERIAL] Read error: {e}")
            time.sleep(0.2)


# ── Video + YOLO thread ───────────────────────────────────────────────────────

def find_camera() -> int:
    for i in range(5):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            cap.release()
            log(f"[CAM] Found camera {i}")
            return i
    return 0


def video_thread(camera_idx: int, yolo_model, aligner=None):
    global _latest_frame, _yolo_fire

    cap = cv2.VideoCapture(camera_idx)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 15)

    # warm-up
    for _ in range(5):
        cap.read()
        time.sleep(0.1)

    if not cap.isOpened():
        log("[CAM] Could not open camera")
        return

    log(f"[CAM] Streaming camera {camera_idx}")
    encode_params = [cv2.IMWRITE_JPEG_QUALITY, MJPEG_QUALITY]
    last_fire_emit = 0.0
    frame_n = 0
    last_fire_targets = []  # cached YOLO result reused between inference frames

    while _running:
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.05)
            continue

        frame_n += 1
        h_frame, w_frame = frame.shape[:2]
        frame_half_w = w_frame // 2

        # YOLO inference — only every YOLO_EVERY_N frames
        fire_count = 0
        fire_targets = last_fire_targets

        if yolo_model is not None and (frame_n % YOLO_EVERY_N == 0):
            fire_targets = []
            results = yolo_model.predict(source=frame, conf=YOLO_CONF,
                                         imgsz=YOLO_IMGSZ, verbose=False)
            for r in results:
                if r.boxes is None:
                    continue
                for b in r.boxes:
                    label = str(r.names.get(int(b.cls[0].item()), "?")).lower()
                    if label not in FIRE_LABELS:
                        continue  # ignore non-fire objects entirely
                    x1, y1, x2, y2 = map(int, b.xyxy[0].tolist())
                    conf  = float(b.conf[0].item())
                    cx = (x1 + x2) // 2
                    cy = (y1 + y2) // 2
                    fire_targets.append({
                        "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                        "cx": cx, "cy": cy, "label": label,
                        "deviation": cx - frame_half_w,
                        "conf": round(conf, 2),
                    })
            last_fire_targets = fire_targets

        fire_count = len(fire_targets)
        # Draw cached boxes on every frame
        for t in fire_targets:
            cv2.rectangle(frame, (t["x1"], t["y1"]), (t["x2"], t["y2"]), (0, 0, 255), 2)
            cv2.putText(frame, f"{t['label']} {t['conf']:.2f}",
                        (t["x1"], max(20, t["y1"] - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        # Pick highest-confidence target as main
        main_target = max(fire_targets, key=lambda t: t["conf"]) if fire_targets else None

        # ── Alignment + approach brain (non-blocking) ──────────────────────
        # Ask the algorithm what to do this frame; send + log any command.
        if aligner is not None:
            with _sensor_lock:
                sensors = dict(_latest_sensors)
            cmd = aligner.update(main_target, w_frame, sensors, time.time())
            if cmd is not None:
                send_command(cmd)   # send_command mirrors it to the log bar

        # Emit YOLO fire status (max 5 times/sec, always on change)
        now = time.time()
        payload = {
            "detected": fire_count > 0,
            "count": fire_count,
            "cx": main_target["cx"] if main_target else None,
            "cy": main_target["cy"] if main_target else None,
            "deviation": main_target["deviation"] if main_target else None,
            "conf": main_target["conf"] if main_target else None,
            "frame_w": w_frame,
            "frame_h": h_frame,
        }
        with _yolo_fire_lock:
            prev_detected = _yolo_fire["detected"]
            _yolo_fire = payload
        changed = prev_detected != payload["detected"]
        if changed or (now - last_fire_emit) >= 0.2:
            socketio.emit("fire_yolo", payload)
            last_fire_emit = now
        if changed:
            if payload["detected"]:
                socketio.emit("log", {"msg": f"🔥 FIRE DETECTED — cx={payload['cx']} dev={payload['deviation']}px conf={payload['conf']}", "cls": "fire"})
            else:
                socketio.emit("log", {"msg": "Fire lost — no detection", "cls": "warn"})

        # Overlay timestamp
        cv2.putText(frame, time.strftime("%H:%M:%S"),
                    (10, frame.shape[0] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        _, jpeg = cv2.imencode(".jpg", frame, encode_params)
        with _frame_lock:
            _latest_frame = jpeg.tobytes()

    cap.release()
    log("[CAM] Camera released")


# ── MJPEG generator ───────────────────────────────────────────────────────────

def _mjpeg_generate():
    while True:
        with _frame_lock:
            frame = _latest_frame
        if frame:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            )
        time.sleep(0.033)  # ~30 fps cap


# ── Flask routes ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/video_feed")
def video_feed():
    return Response(
        _mjpeg_generate(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/sensors")
def sensors():
    from flask import jsonify
    with _sensor_lock:
        return jsonify(_latest_sensors)


# ── SocketIO events ───────────────────────────────────────────────────────────

@socketio.on("command")
def handle_command(data):
    cmd = str(data.get("cmd", "")).strip().upper()
    motion_cmds = {"FWD", "REV", "TURN_L", "TURN_R"}
    simple_cmds = {"STOP", "PUMP_ON", "PUMP_OFF"}

    parts = cmd.split(",")
    base = parts[0]

    if base in simple_cmds:
        send_command(cmd)
    elif base in motion_cmds:
        if len(parts) == 2:
            try:
                spd = int(parts[1])
                if 0 <= spd <= 255:
                    send_command(cmd)
                else:
                    socketio.emit("log", {"msg": f"Speed out of range: {spd} (0-255)", "cls": "warn"})
            except ValueError:
                socketio.emit("log", {"msg": f"Invalid speed: {parts[1]}", "cls": "warn"})
        else:
            socketio.emit("log", {"msg": f"Motion command requires speed: {cmd}", "cls": "warn"})
    elif cmd.startswith("SERVO,"):
        if len(parts) == 2:
            try:
                angle = int(parts[1])
                if 0 <= angle <= 180:
                    send_command(cmd)
                else:
                    socketio.emit("log", {"msg": f"Servo angle out of range: {angle} (0-180)", "cls": "warn"})
            except ValueError:
                socketio.emit("log", {"msg": f"Invalid servo angle: {parts[1]}", "cls": "warn"})
        else:
            socketio.emit("log", {"msg": f"Bad servo command: {cmd}", "cls": "warn"})
    else:
        socketio.emit("log", {"msg": f"Unknown command: {cmd}"})


# ── Entry point ───────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Rover dashboard server")
    p.add_argument("--host",   default="0.0.0.0")
    p.add_argument("--port",   type=int, default=5000)
    p.add_argument("--serial", default=ARDUINO_PORT)
    p.add_argument("--baud",   type=int, default=ARDUINO_BAUD)
    p.add_argument("--camera", type=int, default=None)
    p.add_argument("--no-yolo", action="store_true", help="Disable YOLO inference")
    p.add_argument("--no-align", action="store_true",
                   help="Disable autonomous alignment (observe only, no motor commands)")
    return p.parse_args()


def main():
    global _serial, _running

    args = parse_args()

    # YOLO model
    yolo = None
    if not args.no_yolo:
        try:
            model_path = _ensure_model(DEFAULT_MODEL)
            from ultralytics import YOLO
            yolo = YOLO(str(model_path))
            log(f"[YOLO] Model loaded: {model_path}")
        except Exception as e:
            log(f"[YOLO] Failed to load model: {e}. Continuing without YOLO.")
    else:
        log("[YOLO] Disabled")

    # Serial
    _serial = serial_connect(args.serial, args.baud)

    # Background threads
    t_serial = threading.Thread(target=serial_reader_thread, daemon=True)
    t_serial.start()

    # Alignment brain (pure logic module). Logs its decisions to the dashboard.
    aligner = None
    if not args.no_align:
        def _align_log(msg, cls="info"):
            socketio.emit("log", {"msg": msg, "cls": cls})
        aligner = align_logic.Aligner(logger=_align_log)
        log("[ALIGN] Autonomous alignment ENABLED (Phase 1: align only)")
    else:
        log("[ALIGN] Disabled (observe only — no motor commands)")

    cam_idx = args.camera if args.camera is not None else find_camera()
    t_video = threading.Thread(target=video_thread, args=(cam_idx, yolo, aligner), daemon=True)
    t_video.start()

    log(f"[SERVER] Dashboard at http://{args.host}:{args.port}")
    log(f"[SERVER] PC'den erişim: http://<pi-ip>:{args.port}")

    try:
        socketio.run(app, host=args.host, port=args.port, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        pass
    finally:
        _running = False
        if _serial and _serial.is_open:
            send_command("STOP")
            _serial.close()
        log("[SERVER] Stopped")


if __name__ == "__main__":
    main()
