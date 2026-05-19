#!/usr/bin/env python3
"""
Fire/Smoke detection alert script.

Requirements:
  pip install ultralytics opencv-python huggingface_hub

Usage:
  python fire_smoke_alert.py --source 0

Notes:
- Script always downloads and uses the default fire model from Hugging Face.
- If model loading fails, script exits with error.
- If the same source stays visible for 2 seconds, an alert is printed.
"""

import argparse
import time
from pathlib import Path

import cv2
from ultralytics import YOLO

DEFAULT_HF_REPO = "SalahALHaismawi/yolov26-fire-detection"
DEFAULT_HF_FILE = "best.pt"
MIN_ALERT_CONF = 0.60


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


def download_hf_model(repo_id: str, filename: str, cache_dir: str):
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise RuntimeError(
            "huggingface_hub is not installed. Run: pip install huggingface_hub"
        ) from exc

    local_path = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        cache_dir=cache_dir,
    )
    return Path(local_path)


def main():
    args = parse_args()

    try:
        print(
            f"[INFO] Downloading model from Hugging Face: "
            f"{args.hf_repo}/{args.hf_file}"
        )
        model_path = download_hf_model(args.hf_repo, args.hf_file, args.hf_cache_dir)
        print(f"[INFO] Using downloaded model: {model_path}")
    except Exception as exc:
        raise RuntimeError(
            "Could not load Hugging Face model. Install dependencies/network access and retry."
        ) from exc

    target_classes = {c.strip().lower() for c in args.target_classes.split(",") if c.strip()}
    if not target_classes:
        raise ValueError("At least one target class is required")

    model = YOLO(str(model_path))
    print(f"[INFO] YOLO mode active with model: {model_path}")

    cap = cv2.VideoCapture(to_source(args.source))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open source: {args.source}")

    writer = None
    if args.save:
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 1:
            fps = 25
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(args.output, fourcc, fps, (w, h))

    print("[INFO] Press 'q' to quit.")
    tracks = {}
    next_track_id = 1
    max_match_dist = 90
    max_track_age = 1.0

    while True:
        now = time.time()
        ok, frame = cap.read()
        if not ok:
            break

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
            else:
                tr = tracks[best_id]
                tr["cx"] = cx
                tr["cy"] = cy
                tr["last_seen_ts"] = now

            used_tracks.add(best_id)
            tr = tracks[best_id]
            held_for = now - tr["start_ts"]
            if held_for >= args.alert_hold and not tr["alerted"]:
                print(f"[ALERT] same source '{tr['label']}' persisted for {held_for:.1f}s")
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
            del tracks[tid]

        cv2.imshow("Fire/Smoke Detection", frame)
        if writer is not None:
            writer.write(frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    if writer is not None:
        writer.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
