#!/usr/bin/env python3
"""
Fire detection and auto-alignment rover controller.

Detects fire using YOLO, tracks its location, and automatically
aligns the rover to face the fire by sending motor commands to Arduino.

Usage:
    python3 fire_direct.py [--model-path PATH] [--conf THRESHOLD] [--no-gui]

Requirements:
    pip install ultralytics opencv-python pyserial huggingface_hub
"""

import argparse
import time
import cv2
import serial
import sys
from pathlib import Path
from ultralytics import YOLO

# ---- Constants ----
DEFAULT_LOCAL_MODEL = Path(__file__).resolve().parent / "models" / "best.pt"
DEFAULT_HF_REPO = "SalahALHaismawi/yolov26-fire-detection"
DEFAULT_HF_FILE = "best.pt"
MIN_ALERT_CONF = 0.60
ARDUINO_PORT = "/dev/ttyUSB0"
ARDUINO_BAUD = 115200

# Fire tracking thresholds
MAX_TRACK_DISTANCE = 90      # pixels for centroid matching
MAX_TRACK_AGE = 1.0          # seconds before track dies
ALIGNMENT_THRESHOLD = 80     # pixels from center before turning (wider = less oscillation)

# Pulse turning: turn for short burst then stop, wait for camera feedback
# Increase PULSE_MS if rover barely moves per step
# Decrease PULSE_MS if rover overshoots every time
PULSE_MS = 0.15              # seconds per turn pulse


def log(msg: str):
    """Print timestamped message"""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


def find_camera():
    """Auto-detect camera device"""
    for i in range(5):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            log(f"[CAMERA] Found camera at /dev/video{i}")
            return i
    log("[ERROR] No camera found!")
    return None


def ensure_local_model(repo_id: str, filename: str, local_model_path: Path):
    """Download YOLO model from Hugging Face if not available"""
    if local_model_path.exists():
        log(f"[MODEL] Using existing model: {local_model_path}")
        return local_model_path

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        log("[ERROR] huggingface_hub not installed: pip install huggingface_hub")
        raise

    local_model_path.parent.mkdir(parents=True, exist_ok=True)
    log("[MODEL] Downloading from Hugging Face (one-time setup)...")

    downloaded_path = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        cache_dir=str(Path.home() / ".cache" / "fire-models"),
    )

    log(f"[MODEL] Downloaded to: {downloaded_path}")
    return Path(downloaded_path)


def draw_detection(frame, x1, y1, x2, y2, label, conf):
    """Draw bounding box and label on frame"""
    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
    cv2.putText(frame, f"{label} {conf:.2f}", (x1, max(20, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)


def draw_center_crosshair(frame, cx, cy, size=20, color=(0, 255, 0)):
    """Draw crosshair at frame center"""
    h, w = frame.shape[:2]
    cv_cx, cv_cy = w // 2, h // 2
    cv2.line(frame, (cv_cx - size, cv_cy), (cv_cx + size, cv_cy), color, 2)
    cv2.line(frame, (cv_cx, cv_cy - size), (cv_cx, cv_cy + size), color, 2)


def send_command(ser, cmd):
    """Send command to Arduino"""
    if ser and ser.is_open:
        try:
            ser.write((cmd + '\n').encode())
            log(f"[CMD] → {cmd}")
            return True
        except Exception as e:
            log(f"[ERROR] Failed to send command: {e}")
            return False
    return False


def parse_args():
    parser = argparse.ArgumentParser(description="Fire detection rover auto-alignment")
    parser.add_argument("--model-path", type=str, default=str(DEFAULT_LOCAL_MODEL),
                        help="Path to YOLO model")
    parser.add_argument("--conf", type=float, default=0.60,
                        help="Confidence threshold")
    parser.add_argument("--no-gui", action="store_true",
                        help="Disable GUI window")
    parser.add_argument("--camera", type=int, default=None,
                        help="Camera index (auto-detect if not specified)")
    return parser.parse_args()


def main():
    args = parse_args()
    log("[MAIN] Starting fire detection rover controller...")

    # ---- Setup YOLO Model ----
    try:
        model_path = ensure_local_model(DEFAULT_HF_REPO, DEFAULT_HF_FILE,
                                       Path(args.model_path))
        model = YOLO(str(model_path))
        log("[YOLO] Model loaded successfully")
    except Exception as e:
        log(f"[ERROR] Failed to load model: {e}")
        sys.exit(1)

    # ---- Setup Camera ----
    camera_idx = args.camera if args.camera is not None else find_camera()
    if camera_idx is None:
        sys.exit(1)

    cap = cv2.VideoCapture(camera_idx)
    if not cap.isOpened():
        log(f"[ERROR] Could not open camera {camera_idx}")
        sys.exit(1)
    log(f"[CAMERA] Opened successfully")

    # ---- Setup Arduino Serial ----
    try:
        ser = serial.Serial(ARDUINO_PORT, ARDUINO_BAUD, timeout=1)
        log(f"[ARDUINO] Connected to {ARDUINO_PORT}")
    except serial.SerialException as e:
        log(f"[ERROR] Could not open Arduino: {e}")
        log(f"[ERROR] Make sure Arduino is at {ARDUINO_PORT}")
        ser = None

    # ---- Tracking state ----
    tracks = {}
    next_id = 1
    frame_idx = 0
    last_cmd = None
    last_cmd_time = 0.0
    CMD_RATE_LIMIT = 0.20        # seconds between same command repeats
    last_pulse_time = 0.0        # time of last turn pulse
    PULSE_COOLDOWN = PULSE_MS + 0.10  # wait for camera to catch up after pulse

    # Allow camera sensor to initialize — macOS needs several frames before reads succeed
    for _ in range(5):
        cap.read()
        time.sleep(0.1)

    show_gui = not args.no_gui
    if show_gui:
        log("[GUI] Display enabled. Press 'q' to quit.")
    else:
        log("[GUI] Headless mode. Use Ctrl+C to stop.")

    try:
        while True:
            now = time.time()
            ok, frame = cap.read()
            if not ok:
                log("[ERROR] Could not read frame")
                break

            frame_idx += 1
            h, w = frame.shape[:2]
            frame_cx, frame_cy = w // 2, h // 2

            # ---- YOLO Detection ----
            detections = []
            results = model.predict(source=frame, conf=args.conf, verbose=False)

            for r in results:
                if r.boxes is None:
                    continue
                for b in r.boxes:
                    cls_id = int(b.cls[0].item())
                    conf = float(b.conf[0].item())
                    label = str(r.names.get(cls_id, cls_id)).lower()

                    if conf < MIN_ALERT_CONF:
                        continue

                    x1, y1, x2, y2 = map(int, b.xyxy[0].tolist())
                    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

                    draw_detection(frame, x1, y1, x2, y2, label, conf)
                    detections.append((label, x1, y1, x2, y2, cx, cy, conf))

                    log(f"[DETECT] frame={frame_idx} {label} conf={conf:.2f} center=({cx},{cy})")

            # ---- Track Management (Round-Robin) ----
            used = set()
            for label, x1, y1, x2, y2, cx, cy, conf in detections:
                # Find best matching track
                best_id = None
                best_dist2 = None

                for tid, tr in tracks.items():
                    if tid in used or tr["label"] != label:
                        continue
                    dx = cx - tr["cx"]
                    dy = cy - tr["cy"]
                    d2 = dx * dx + dy * dy

                    if d2 <= MAX_TRACK_DISTANCE ** 2 and (best_dist2 is None or d2 < best_dist2):
                        best_id = tid
                        best_dist2 = d2

                # Create new track or update existing
                if best_id is None:
                    best_id = next_id
                    next_id += 1
                    tracks[best_id] = {
                        "label": label,
                        "cx": cx,
                        "cy": cy,
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2,
                        "conf": conf,
                        "start_ts": now,
                        "last_seen_ts": now,
                        "alerted": False,
                    }
                    log(f"[TRACK] New fire track id={best_id} center=({cx},{cy})")
                else:
                    tracks[best_id].update({
                        "cx": cx,
                        "cy": cy,
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2,
                        "conf": conf,
                        "last_seen_ts": now,
                    })

                used.add(best_id)

            # ---- Remove stale tracks ----
            stale = [t for t, tr in tracks.items()
                    if now - tr["last_seen_ts"] > MAX_TRACK_AGE]
            for tid in stale:
                log(f"[TRACK] Stale fire track id={tid} removed")
                del tracks[tid]

            # ---- Motor Control Logic ----
            def rate_limited_cmd(cmd):
                nonlocal last_cmd, last_cmd_time
                if cmd == last_cmd and (now - last_cmd_time) < CMD_RATE_LIMIT:
                    return
                send_command(ser, cmd)
                last_cmd = cmd
                last_cmd_time = now

            if tracks:
                main_track = max(tracks.values(), key=lambda t: t["conf"])
                fire_cx = main_track["cx"]
                deviation = fire_cx - frame_cx

                log(f"[ALIGN] Fire at x={fire_cx}, frame center x={frame_cx}, deviation={deviation}")

                if abs(deviation) > ALIGNMENT_THRESHOLD:
                    # Pulse: only turn if cooldown elapsed (rover stopped + camera settled)
                    if (now - last_pulse_time) >= PULSE_COOLDOWN:
                        turn_cmd = "TURN_L" if deviation < 0 else "TURN_R"
                        send_command(ser, turn_cmd)
                        last_cmd = turn_cmd
                        last_cmd_time = now
                        time.sleep(PULSE_MS)        # turn for fixed burst
                        send_command(ser, "STOP")
                        last_cmd = "STOP"
                        last_pulse_time = now       # start cooldown
                else:
                    # Fire centered — hold position
                    rate_limited_cmd("STOP")

                cv2.rectangle(frame, (main_track["x1"], main_track["y1"]),
                            (main_track["x2"], main_track["y2"]), (0, 255, 0), 3)
                cv2.putText(frame, "TARGET",
                           (main_track["x1"], main_track["y1"] - 15),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            else:
                # No fire — stop then search-turn every 2 sec
                if last_cmd not in ("STOP", "TURN_L") or last_cmd == "FWD":
                    rate_limited_cmd("STOP")
                if frame_idx % 60 == 0:
                    send_command(ser, "TURN_L")
                    last_cmd = "TURN_L"
                    last_cmd_time = now

            # Draw frame center crosshair
            draw_center_crosshair(frame, frame_cx, frame_cy)

            # Add frame info
            cv2.putText(frame, f"Frame {frame_idx} | Tracks: {len(tracks)}",
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

            # Display
            if show_gui:
                cv2.imshow("Fire Direct - Rover Auto-Alignment", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    log("[GUI] 'q' pressed. Exiting...")
                    break

    except KeyboardInterrupt:
        log("[MAIN] Interrupted by user")
    finally:
        # Cleanup
        log("[CLEANUP] Stopping rover...")
        send_command(ser, "STOP")

        cap.release()
        if ser and ser.is_open:
            ser.close()
        cv2.destroyAllWindows()

        log("[CLEANUP] Done. Goodbye!")


if __name__ == "__main__":
    main()
