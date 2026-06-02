"""
YOLO worker thread.

Görevler:
  - Kameradan frame okur
  - YOLO inference çalıştırır
  - Centroid tabanlı track yönetir
  - Annotated frame'i frame_q'ya koyar (GUI için)
  - Track snapshot'ı shared_tracks'e yazar (arduino_controller için)
"""
import queue
import time

import cv2

from .config import log, MIN_ALERT_CONF


def draw_box(frame, x1: int, y1: int, x2: int, y2: int,
             label: str, conf: float) -> None:
    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
    cv2.putText(frame, f"{label} {conf:.2f}", (x1, max(20, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)


def yolo_worker(cap, model, args, target_classes: set,
                shared_tracks: dict, tracks_lock, stop_event,
                frame_q: queue.Queue, writer) -> None:
    """
    YOLO thread ana döngüsü.
    cap, model, writer — sadece bu thread erişir (thread-safe değil).
    shared_tracks — tracks_lock altında güncellenir.
    frame_q — maxsize=2, doluysa eski frame düşürülür.
    """
    tracks    = {}
    next_id   = 1
    max_dist  = 90     # track eşleştirme için maksimum piksel mesafesi
    max_age   = 1.0    # sn — bu süre görünmeyen track silinir
    frame_idx = 0
    eff_conf  = max(args.conf, MIN_ALERT_CONF)

    while not stop_event.is_set():
        ok, frame = cap.read()
        if not ok:
            log("[YOLO] Kamera akışı bitti.")
            stop_event.set()
            break

        now = time.time()
        frame_idx += 1
        if frame_idx % 30 == 0:
            log(f"[YOLO] frame #{frame_idx}")

        # ---- Inference ----
        detections = []
        for r in model.predict(source=frame, conf=eff_conf, verbose=False):
            if r.boxes is None:
                continue
            for b in r.boxes:
                cls_id = int(b.cls[0].item())
                conf   = float(b.conf[0].item())
                label  = str(r.names.get(cls_id, cls_id)).lower()
                if label not in target_classes or conf < MIN_ALERT_CONF:
                    continue
                x1, y1, x2, y2 = map(int, b.xyxy[0].tolist())
                draw_box(frame, x1, y1, x2, y2, label, conf)
                log(f"[DETECT] f={frame_idx} {label} {conf:.2f} ({x1},{y1},{x2},{y2})")
                detections.append((label, x1, y1, x2, y2, (x1+x2)//2, (y1+y2)//2))

        # ---- Track güncelle ----
        used = set()
        for label, x1, y1, x2, y2, cx, cy in detections:
            best_id, best_d2 = None, None
            for tid, tr in tracks.items():
                if tid in used or tr["label"] != label:
                    continue
                d2 = (cx - tr["cx"])**2 + (cy - tr["cy"])**2
                if d2 <= max_dist**2 and (best_d2 is None or d2 < best_d2):
                    best_id, best_d2 = tid, d2

            if best_id is None:
                best_id = next_id
                next_id += 1
                tracks[best_id] = {
                    "label": label, "cx": cx, "cy": cy,
                    "start_ts": now, "last_seen_ts": now, "alerted": False,
                }
                log(f"[TRACK] yeni id={best_id} {label} ({cx},{cy})")
            else:
                tracks[best_id].update({"cx": cx, "cy": cy, "last_seen_ts": now})

            used.add(best_id)
            tr = tracks[best_id]
            if now - tr["start_ts"] >= args.alert_hold and not tr["alerted"]:
                tr["alerted"] = True
                log(f"[ALERT] '{label}' id={best_id} alerted")
            if tr["alerted"]:
                cv2.putText(frame, "ALERT",
                            (x1, min(frame.shape[0] - 10, y2 + 20)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        # Stale track'leri temizle
        stale = [t for t, tr in tracks.items() if now - tr["last_seen_ts"] > max_age]
        for tid in stale:
            log(f"[TRACK] stale id={tid} silindi")
            del tracks[tid]

        # ---- Paylaş (kısa lock) ----
        with tracks_lock:
            shared_tracks.clear()
            shared_tracks.update(tracks)

        if writer:
            writer.write(frame)

        try:
            frame_q.put_nowait(frame)
        except queue.Full:
            pass   # display yavaşsa en eski frame'i at
