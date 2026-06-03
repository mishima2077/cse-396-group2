#!/usr/bin/env python3
"""
Fire centering script (standalone test — no Arduino connection).

Kamera üzerinden ateşi tespit eder, visual servoing ile merkeze alır.
Ateş ortalandığında ekranda ve terminalde bildirim gösterir.

Requirements:
  pip install ultralytics opencv-python huggingface_hub

Usage:
  python fire_centering.py --source 0
  python fire_centering.py --source 0 --no-gui
"""

import argparse
import os
import time
from pathlib import Path

import cv2
from ultralytics import YOLO

# ── Model ayarları ────────────────────────────────────────────────────────────
DEFAULT_HF_REPO   = "SalahALHaismawi/yolov26-fire-detection"
DEFAULT_HF_FILE   = "best.pt"
DEFAULT_LOCAL_MODEL = Path(__file__).resolve().parent / "models" / "best.pt"

# ── Algılama ayarları ─────────────────────────────────────────────────────────
MIN_CONF      = 0.60   # minimum güven eşiği

# ── Ortalama ayarları ─────────────────────────────────────────────────────────
DEAD_ZONE_PX  = 40     # ±40px tolerans — bu aralıkta "ortalandı" sayılır
CENTERED_HOLD = 1.5    # kaç saniye bu aralıkta kalırsa "stabil ortalandı" denir


def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


def parse_args():
    parser = argparse.ArgumentParser(description="Fire centering — standalone test")
    parser.add_argument("--hf-repo",      default=DEFAULT_HF_REPO)
    parser.add_argument("--hf-file",      default=DEFAULT_HF_FILE)
    parser.add_argument("--hf-cache-dir", default=str(Path.home() / ".cache" / "fire-smoke-models"))
    parser.add_argument("--model-path",   default=str(DEFAULT_LOCAL_MODEL))
    parser.add_argument("--source",       default="0")
    parser.add_argument("--conf",         type=float, default=0.60)
    parser.add_argument("--no-gui",       action="store_true")
    return parser.parse_args()


# ── Model yükleme ─────────────────────────────────────────────────────────────

def write_file_atomic(src_path: Path, dst_path: Path):
    tmp = dst_path.with_suffix(dst_path.suffix + ".tmp")
    with src_path.open("rb") as s, tmp.open("wb") as t:
        while chunk := s.read(1 << 20):
            t.write(chunk)
        t.flush()
        os.fsync(t.fileno())
    os.replace(tmp, dst_path)
    fd = os.open(str(dst_path.parent), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def ensure_local_model(repo_id, filename, cache_dir, local_path: Path) -> Path:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as e:
        raise RuntimeError("huggingface_hub yüklü değil: pip install huggingface_hub") from e

    if local_path.exists():
        log(f"[MODEL] Mevcut model kullanılıyor: {local_path}")
        return local_path

    local_path.parent.mkdir(parents=True, exist_ok=True)
    log("[MODEL] Hugging Face'den indiriliyor (ilk çalıştırma)…")
    dl = hf_hub_download(repo_id=repo_id, filename=filename, cache_dir=cache_dir)
    write_file_atomic(Path(dl), local_path)
    log(f"[MODEL] İndirildi ve kaydedildi: {local_path}")
    return local_path


# ── Yardımcı fonksiyonlar ─────────────────────────────────────────────────────

def to_source(src: str):
    return int(src) if src.isdigit() else src


def get_turn_direction(fire_cx: int, frame_width: int) -> str:
    """
    Ateşin merkeze göre konumuna bakarak hangi yöne dönülmesi gerektiğini döndürür.
    Dönüş yok → "CENTERED"
    Sola dön  → "TURN_L"
    Sağa dön  → "TURN_R"
    """
    center_x = frame_width // 2
    error = fire_cx - center_x
    if abs(error) <= DEAD_ZONE_PX:
        return "CENTERED"
    return "TURN_L" if error < 0 else "TURN_R"


def draw_hud(frame, fire_cx: int, fire_cy: int,
             x1: int, y1: int, x2: int, y2: int,
             direction: str, conf: float,
             centered_since: float, now: float):
    """
    Frame üzerine bounding box, yön oku, merkez çizgisi ve durum bilgisi çizer.
    """
    h, w = frame.shape[:2]
    cx_frame = w // 2

    # Merkez dikey çizgi (beyaz, kesik)
    for y in range(0, h, 20):
        cv2.line(frame, (cx_frame, y), (cx_frame, min(y + 10, h)), (200, 200, 200), 1)

    # Dead zone şeritleri (sarı)
    cv2.line(frame, (cx_frame - DEAD_ZONE_PX, 0),
             (cx_frame - DEAD_ZONE_PX, h), (0, 200, 255), 1)
    cv2.line(frame, (cx_frame + DEAD_ZONE_PX, 0),
             (cx_frame + DEAD_ZONE_PX, h), (0, 200, 255), 1)

    # Ateş bounding box
    box_color = (0, 255, 0) if direction == "CENTERED" else (0, 80, 255)
    cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
    cv2.putText(frame, f"fire {conf:.2f}", (x1, max(18, y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, box_color, 2)

    # Ateşin merkez noktası
    cv2.circle(frame, (fire_cx, fire_cy), 5, (0, 255, 255), -1)

    # Ateş merkezinden frame merkezine yatay ok
    cv2.arrowedLine(frame, (fire_cx, fire_cy), (cx_frame, fire_cy),
                    (0, 255, 255), 2, tipLength=0.2)

    # Yön bilgisi — sol üst köşe
    if direction == "CENTERED":
        hold = now - centered_since if centered_since else 0.0
        remaining = max(0.0, CENTERED_HOLD - hold)
        label = f"CENTERED  ({remaining:.1f}s)" if remaining > 0 else "CENTERED"
        color = (0, 255, 0)
    else:
        arrow = "<-- SOL DON" if direction == "TURN_L" else "SAG DON -->"
        label = arrow
        color = (0, 80, 255)

    cv2.putText(frame, label, (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

    # Hata değeri
    error = fire_cx - cx_frame
    cv2.putText(frame, f"hata: {error:+d} px", (10, 58),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)


def draw_alert_banner(frame):
    """
    "ATES ORTALANDI" büyük banner çizer.
    """
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, h // 2 - 50), (w, h // 2 + 50), (0, 180, 0), -1)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)
    cv2.putText(frame, "ATES ORTALANDI!", (w // 2 - 200, h // 2 + 15),
                cv2.FONT_HERSHEY_DUPLEX, 1.2, (255, 255, 255), 3)


def draw_no_fire(frame):
    h, w = frame.shape[:2]
    cv2.putText(frame, "Ates bulunamadi...", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 100, 255), 2)


# ── Ana döngü ─────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    log("[BAŞLANGIÇ] Fire Centering — standalone test modu")

    # Model hazırla
    try:
        local_path = Path(args.model_path).expanduser().resolve()
        model_path = ensure_local_model(
            args.hf_repo, args.hf_file, args.hf_cache_dir, local_path
        )
    except Exception as exc:
        log(f"[HATA] Model yüklenemedi: {exc}")
        raise

    model = YOLO(str(model_path))
    log(f"[MODEL] YOLO yüklendi: {model_path}")

    cap = cv2.VideoCapture(to_source(args.source))
    if not cap.isOpened():
        raise RuntimeError(f"Kamera açılamadı: {args.source}")
    log(f"[KAMERA] Açıldı: {args.source}")

    show_gui = not args.no_gui
    if show_gui:
        log("[GUI] Aktif — çıkmak için 'q'")
    else:
        log("[GUI] Kapalı — çıkmak için Ctrl+C")

    frame_width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))

    # Durum değişkenleri
    centered_since: float = 0.0   # ne zamandan beri centered konumda
    alert_fired   : bool  = False  # bu oturum için alert gönderildi mi
    last_direction: str   = ""     # önceki yön komutu (gereksiz tekrarı önler)
    frame_idx     : int   = 0

    while True:
        now = time.time()
        ok, frame = cap.read()
        if not ok:
            log("[BİTİŞ] Frame okunamadı veya akış sona erdi.")
            break

        frame_idx += 1
        fw = frame.shape[1]   # gerçek genişlik (frame'den al)

        # ── YOLO inference ────────────────────────────────────────────────────
        results = model.predict(source=frame, conf=max(args.conf, MIN_CONF), verbose=False)

        best = None   # en yüksek güvenli "fire" tespiti
        for r in results:
            for b in r.boxes or []:
                cls_id = int(b.cls[0].item())
                conf   = float(b.conf[0].item())
                label  = str(r.names.get(cls_id, cls_id)).lower()
                if label != "fire" or conf < MIN_CONF:
                    continue
                x1, y1, x2, y2 = map(int, b.xyxy[0].tolist())
                if best is None or conf > best[4]:
                    best = (x1, y1, x2, y2, conf)

        # ── Yön hesabı & durum güncellemesi ───────────────────────────────────
        if best is not None:
            x1, y1, x2, y2, conf = best
            fire_cx = (x1 + x2) // 2
            fire_cy = (y1 + y2) // 2

            direction = get_turn_direction(fire_cx, fw)

            # Yön değiştiyse terminale yaz
            if direction != last_direction:
                log(f"[KOMUT] {direction}  (ateş cx={fire_cx}, hata={fire_cx - fw//2:+d}px)")
                last_direction = direction

            # Centered zamanlayıcısı
            if direction == "CENTERED":
                if centered_since == 0.0:
                    centered_since = now
                    log("[DURUM] Ateş dead-zone'a girdi, sayaç başladı…")

                held = now - centered_since
                if held >= CENTERED_HOLD and not alert_fired:
                    log("=" * 55)
                    log("  [ALERT] ATES ORTALANDI — flame sensör onayı bekleniyor")
                    log("=" * 55)
                    alert_fired = True
            else:
                # Dead-zone'dan çıktı, sayacı sıfırla
                if centered_since != 0.0:
                    log("[DURUM] Dead-zone'dan çıkıldı, sayaç sıfırlandı.")
                centered_since = 0.0
                alert_fired    = False

            # HUD çiz
            draw_hud(frame, fire_cx, fire_cy, x1, y1, x2, y2,
                     direction, conf, centered_since, now)

            if alert_fired:
                draw_alert_banner(frame)

        else:
            # Ateş yok → sayacı sıfırla
            if centered_since != 0.0:
                log("[DURUM] Ateş kaybedildi, sayaç sıfırlandı.")
            centered_since = 0.0
            alert_fired    = False
            last_direction = ""
            draw_no_fire(frame)

        # ── Göster ────────────────────────────────────────────────────────────
        if show_gui:
            cv2.imshow("Fire Centering — Test", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                log("[ÇIKIŞ] 'q' basıldı.")
                break

    cap.release()
    cv2.destroyAllWindows()
    log("[BİTİŞ] Kaynaklar serbest bırakıldı.")


if __name__ == "__main__":
    main()