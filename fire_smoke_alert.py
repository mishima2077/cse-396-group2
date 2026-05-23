#!/usr/bin/env python3
"""
Fire/Smoke detection alert script.

Requirements:
  pip install ultralytics opencv-python huggingface_hub

Usage:
  python fire_smoke_alert.py --source 0
  python fire_smoke_alert.py --source 0 --no-gui

Notes:
- Script stores model at a fixed local path on first run, then always reuses it.
- If model loading fails, script exits with error.
- If the same source stays visible for 2 seconds, an alert is printed.
"""

import argparse
import os
import time
from pathlib import Path

import cv2
from ultralytics import YOLO

DEFAULT_HF_REPO = "SalahALHaismawi/yolov26-fire-detection"
DEFAULT_HF_FILE = "best.pt"
DEFAULT_LOCAL_MODEL = Path(__file__).resolve().parent / "models" / "best.pt"
MIN_ALERT_CONF = 0.60


def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


def parse_args():
    parser = argparse.ArgumentParser(description="Fire/Smoke detection with alerts")
    parser.add_argument(
        "--hf-repo",
        type=str,
        default=DEFAULT_HF_REPO,
        help="Hugging Face repo id used for model download",
    )
    parser.add_argument(
        "--hf-file",
        type=str,
        default=DEFAULT_HF_FILE,
        help="Filename inside --hf-repo to download",
    )
    parser.add_argument(
        "--hf-cache-dir",
        type=str,
        default=str(Path.home() / ".cache" / "fire-smoke-models"),
        help="Cache directory for Hugging Face model downloads",
    )
    parser.add_argument(
        "--model-path",
        type=str,
        default=str(DEFAULT_LOCAL_MODEL),
        help="Fixed local model path (downloaded once, then reused)",
    )
    parser.add_argument(
        "--source",
        type=str,
        default="0",
        help="Camera index (0,1,...) or video path",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.60,
        help="Confidence threshold (minimum 0.60 for alerts)",
    )
    parser.add_argument(
        "--target-classes",
        type=str,
        default="fire",
        help="Comma-separated class names to alert on",
    )
    parser.add_argument(
        "--alert-hold",
        type=float,
        default=2.0,
        help="Seconds a same source must persist before alert",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save annotated output video",
    )
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="Disable GUI window (useful on headless Raspberry/SSH)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="alert_output.mp4",
        help="Output path when --save is used",
    )
    return parser.parse_args()


def draw_box(frame, x1, y1, x2, y2, label, conf):
    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
    text = f"{label} {conf:.2f}"
    cv2.putText(frame, text, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)


def to_source(src: str):
    if src.isdigit():
        return int(src)
    return src


def write_file_atomic(src_path: Path, dst_path: Path):
    tmp_path = dst_path.with_suffix(dst_path.suffix + ".tmp")
    with src_path.open("rb") as src_f, tmp_path.open("wb") as tmp_f:
        while True:
            chunk = src_f.read(1024 * 1024)
            if not chunk:
                break
            tmp_f.write(chunk)
        tmp_f.flush()
        os.fsync(tmp_f.fileno())

    os.replace(tmp_path, dst_path)

    # Ensure directory metadata is also persisted.
    dir_fd = os.open(str(dst_path.parent), os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def ensure_local_model(repo_id: str, filename: str, cache_dir: str, local_model_path: Path):
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise RuntimeError(
            "huggingface_hub is not installed. Run: pip install huggingface_hub"
        ) from exc

    if local_model_path.exists():
        log(f"[INFO] Using existing local model: {local_model_path}")
        return local_model_path

    local_model_path.parent.mkdir(parents=True, exist_ok=True)
    log("[INFO] Local model not found. Downloading from Hugging Face (one-time setup)...")
    downloaded_path = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        cache_dir=cache_dir,
    )

    # Copy to deterministic local path with atomic write for power-loss safety.
    write_file_atomic(Path(downloaded_path), local_model_path)
    log(f"[INFO] Model downloaded and stored at: {local_model_path}")
    return local_model_path


def main():
    args = parse_args()
    log(
        "[INFO] Starting with "
        f"source={args.source}, conf={args.conf}, target_classes={args.target_classes}, "
        f"alert_hold={args.alert_hold}, no_gui={args.no_gui}, save={args.save}"
    )

    try:
        local_model_path = Path(args.model_path).expanduser().resolve()
        log(
            f"[INFO] Preparing model: {args.hf_repo}/{args.hf_file} -> {local_model_path}"
        )
        model_path = ensure_local_model(
            args.hf_repo,
            args.hf_file,
            args.hf_cache_dir,
            local_model_path,
        )
    except Exception as exc:
        log(f"[ERROR] Model prepare failed: {exc}")
        raise RuntimeError(
            "Could not load Hugging Face model. Install dependencies/network access and retry."
        ) from exc

    target_classes = {c.strip().lower() for c in args.target_classes.split(",") if c.strip()}
    if not target_classes:
        raise ValueError("At least one target class is required")
    log(f"[INFO] Target classes: {sorted(target_classes)}")

    model = YOLO(str(model_path))
    log(f"[INFO] YOLO mode active with model: {model_path}")
    show_gui = not args.no_gui

    cap = cv2.VideoCapture(to_source(args.source))
    if not cap.isOpened():
        log(f"[ERROR] Could not open source: {args.source}")
        raise RuntimeError(f"Could not open source: {args.source}")
    log(f"[INFO] Video source opened: {args.source}")

    writer = None
    if args.save:
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 1:
            fps = 25
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(args.output, fourcc, fps, (w, h))
        log(f"[INFO] Video writer enabled: {args.output} ({w}x{h} @ {fps:.2f}fps)")

    if show_gui:
        log("[INFO] GUI mode active. Press 'q' to quit.")
    else:
        log("[INFO] No-GUI mode active. Use Ctrl+C to stop.")
    tracks = {}
    next_track_id = 1
    max_match_dist = 90
    max_track_age = 1.0
    frame_idx = 0

    while True:
        now = time.time()
        ok, frame = cap.read()
        if not ok:
            log("[INFO] Stream ended or frame could not be read. Stopping.")
            break
        frame_idx += 1
        if frame_idx % 30 == 0:
            log(f"[INFO] Processing frame #{frame_idx}")

        detections = []
        effective_conf = max(args.conf, MIN_ALERT_CONF)
        results = model.predict(source=frame, conf=effective_conf, verbose=False)
        for r in results:
            names = r.names
            boxes = r.boxes
            if boxes is None:
                continue

            for b in boxes:
                cls_id = int(b.cls[0].item())
                conf = float(b.conf[0].item())
                label = str(names.get(cls_id, cls_id)).lower()

                if label not in target_classes or conf < MIN_ALERT_CONF:
                    continue

                x1, y1, x2, y2 = map(int, b.xyxy[0].tolist())
                draw_box(frame, x1, y1, x2, y2, label, conf)
                log(f"[DETECT] frame={frame_idx} label={label} conf={conf:.2f} box=({x1},{y1},{x2},{y2})")
                cx = (x1 + x2) // 2
                cy = (y1 + y2) // 2
                detections.append((label, x1, y1, x2, y2, cx, cy))

        used_tracks = set()
        for label, x1, y1, x2, y2, cx, cy in detections:
            best_id = None
            best_dist2 = None
            for tid, tr in tracks.items():
                if tid in used_tracks or tr["label"] != label:
                    continue

                dx = cx - tr["cx"]
                dy = cy - tr["cy"]
                dist2 = dx * dx + dy * dy
                if dist2 <= max_match_dist * max_match_dist and (best_dist2 is None or dist2 < best_dist2):
                    best_id = tid
                    best_dist2 = dist2

            if best_id is None:
                best_id = next_track_id
                next_track_id += 1
                tracks[best_id] = {
                    "label": label,
                    "cx": cx,
                    "cy": cy,
                    "start_ts": now,
                    "last_seen_ts": now,
                    "alerted": False,
                }
                log(f"[TRACK] New track id={best_id} label={label} center=({cx},{cy})")
            else:
                tr = tracks[best_id]
                tr["cx"] = cx
                tr["cy"] = cy
                tr["last_seen_ts"] = now
                log(f"[TRACK] Update track id={best_id} label={label} center=({cx},{cy})")

            used_tracks.add(best_id)
            tr = tracks[best_id]
            held_for = now - tr["start_ts"]
            if held_for >= args.alert_hold and not tr["alerted"]:
                log(f"[ALERT] same source '{tr['label']}' persisted for {held_for:.1f}s (track id={best_id})")
                tr["alerted"] = True

            if tr["alerted"]:
                cv2.putText(
                    frame,
                    "ALERT",
                    (x1, min(frame.shape[0] - 10, y2 + 20)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 0, 255),
                    2,
                )

        stale_ids = []
        for tid, tr in tracks.items():
            if now - tr["last_seen_ts"] > max_track_age:
                stale_ids.append(tid)
        for tid in stale_ids:
            log(f"[TRACK] Removing stale track id={tid}")
            del tracks[tid]

        if show_gui:
            cv2.imshow("Fire/Smoke Detection", frame)
        if writer is not None:
            writer.write(frame)

        if show_gui and (cv2.waitKey(1) & 0xFF == ord("q")):
            log("[INFO] 'q' pressed. Exiting.")
            break

    cap.release()
    if writer is not None:
        writer.release()
    cv2.destroyAllWindows()
    log("[INFO] Resources released. Bye.")


if __name__ == "__main__":
    main()