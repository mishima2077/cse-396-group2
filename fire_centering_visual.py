#!/usr/bin/env python3
"""
Kod 1 — Visual Servoing ile ateş ortalama.

Davranış:
  - Ateş yok  → 45° adımlarla kendi etrafında tara (her adımda 500ms bekle)
  - Ateş var  → visual servoing: dead zone'a girene kadar TURN_L/TURN_R gönder

Sabitler:
  MOTOR_SPEED = 255  (Config.h'de)
  45° = 600ms dönüş süresi
  FOV = 55°, DEAD_ZONE = 40px

Requirements:
  pip install ultralytics opencv-python huggingface_hub pyserial

Usage:
  python fire_centering_visual.py --source 0 --port /dev/ttyUSB0
"""

import argparse
import os
import time
from pathlib import Path

import cv2
import serial
import serial.tools.list_ports
from ultralytics import YOLO

# ── Model ayarları ────────────────────────────────────────────────────────────
DEFAULT_HF_REPO     = "SalahALHaismawi/yolov26-fire-detection"
DEFAULT_HF_FILE     = "best.pt"
DEFAULT_LOCAL_MODEL = Path(__file__).resolve().parent / "models" / "best.pt"

# ── Algılama ──────────────────────────────────────────────────────────────────
MIN_CONF      = 0.60

# ── Visual servoing ───────────────────────────────────────────────────────────
DEAD_ZONE_PX  = 40      # ±40px tolerans
CENTERED_HOLD = 1.5     # saniye — bu kadar stabil kalırsa "ortalandı"
CMD_INTERVAL  = 0.15    # saniye — komut gönderme sıklığı

# ── Tarama (ateş yokken) ──────────────────────────────────────────────────────
SCAN_TURN_MS  = 600     # 45° dönüş süresi (ms)
SCAN_WAIT_MS  = 500     # dönüş sonrası görüntü bekleme süresi (ms)

# ── Serial ────────────────────────────────────────────────────────────────────
SERIAL_BAUD   = 115200


def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


def parse_args():
    parser = argparse.ArgumentParser(description="Kod 1 — Visual Servoing")
    parser.add_argument("--hf-repo",      default=DEFAULT_HF_REPO)
    parser.add_argument("--hf-file",      default=DEFAULT_HF_FILE)
    parser.add_argument("--hf-cache-dir", default=str(Path.home() / ".cache" / "fire-smoke-models"))
    parser.add_argument("--model-path",   default=str(DEFAULT_LOCAL_MODEL))
    parser.add_argument("--source",       default="0")
    parser.add_argument("--conf",         type=float, default=0.60)
    parser.add_argument("--no-gui",       action="store_true")
    parser.add_argument("--port",         type=str, default=None,
                        help="Arduino port (örn. /dev/ttyUSB0)")
    return parser.parse_args()


# ── Serial ────────────────────────────────────────────────────────────────────

def find_arduino_port():
    KEYWORDS = ("arduino", "ch340", "ch341", "cp210", "ftdi", "usb serial")
    for p in serial.tools.list_ports.comports():
        desc = (p.description or "").lower()
        mfr  = (p.manufacturer or "").lower()
        if any(k in desc or k in mfr for k in KEYWORDS):
            return p.device
    for c in ("/dev/ttyUSB0", "/dev/ttyACM0"):
        if Path(c).exists():
            return c
    return None


def open_serial(port):
    if port is None:
        port = find_arduino_port()
    if port is None:
        raise RuntimeError("Arduino portu bulunamadı. --port ile belirtin.")
    log(f"[SERIAL] Bağlanıyor: {port}  baud={SERIAL_BAUD}")
    ser = serial.Serial(port, SERIAL_BAUD, timeout=0.1)
    time.sleep(2.0)
    ser.reset_input_buffer()
    log(f"[SERIAL] Bağlantı kuruldu: {port}")
    return ser


def send_cmd(ser, cmd: str):
    try:
        ser.write((cmd + "\n").encode("ascii"))
    except serial.SerialException as e:
        log(f"[SERIAL HATA] {cmd}: {e}")


# ── Model ─────────────────────────────────────────────────────────────────────

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
        raise RuntimeError("pip install huggingface_hub") from e
    if local_path.exists():
        log(f"[MODEL] Mevcut: {local_path}")
        return local_path
    local_path.parent.mkdir(parents=True, exist_ok=True)
    log("[MODEL] İndiriliyor…")
    dl = hf_hub_download(repo_id=repo_id, filename=filename, cache_dir=cache_dir)
    write_file_atomic(Path(dl), local_path)
    log(f"[MODEL] Kaydedildi: {local_path}")
    return local_path


# ── Yardımcılar ───────────────────────────────────────────────────────────────

def to_source(src: str):
    return int(src) if src.isdigit() else src


def detect_fire(model, frame, conf_thresh: float):
    """En yüksek güvenli 'fire' tespitini döndürür. Yoksa None."""
    results = model.predict(source=frame, conf=conf_thresh, verbose=False)
    best = None
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
    return best


def get_direction(fire_cx: int, fw: int) -> str:
    error = fire_cx - fw // 2
    if abs(error) <= DEAD_ZONE_PX:
        return "CENTERED"
    return "TURN_L" if error < 0 else "TURN_R"


# ── HUD ───────────────────────────────────────────────────────────────────────

def draw_hud(frame, fire_cx, fire_cy, x1, y1, x2, y2,
             direction, conf, centered_since, now, mode: str):
    h, w = frame.shape[:2]
    cx_frame = w // 2

    # Merkez çizgisi
    for y in range(0, h, 20):
        cv2.line(frame, (cx_frame, y), (cx_frame, min(y+10, h)), (200,200,200), 1)

    # Dead zone
    cv2.line(frame, (cx_frame-DEAD_ZONE_PX, 0), (cx_frame-DEAD_ZONE_PX, h), (0,200,255), 1)
    cv2.line(frame, (cx_frame+DEAD_ZONE_PX, 0), (cx_frame+DEAD_ZONE_PX, h), (0,200,255), 1)

    # Mod etiketi (sağ üst)
    cv2.putText(frame, f"MOD: {mode}", (w-200, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,0), 2)

    # Bounding box
    box_color = (0,255,0) if direction == "CENTERED" else (0,80,255)
    cv2.rectangle(frame, (x1,y1), (x2,y2), box_color, 2)
    cv2.putText(frame, f"fire {conf:.2f}", (x1, max(18, y1-6)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, box_color, 2)

    cv2.circle(frame, (fire_cx, fire_cy), 5, (0,255,255), -1)
    cv2.arrowedLine(frame, (fire_cx, fire_cy), (cx_frame, fire_cy),
                    (0,255,255), 2, tipLength=0.2)

    if direction == "CENTERED":
        hold = now - centered_since if centered_since else 0.0
        remaining = max(0.0, CENTERED_HOLD - hold)
        label = f"CENTERED ({remaining:.1f}s)" if remaining > 0 else "CENTERED"
        color = (0,255,0)
    else:
        label = "<-- SOL DON" if direction == "TURN_L" else "SAG DON -->"
        color = (0,80,255)

    cv2.putText(frame, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
    error = fire_cx - cx_frame
    cv2.putText(frame, f"hata: {error:+d} px", (10, 58),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200,200,200), 1)


def draw_scan_hud(frame, step: int):
    h, w = frame.shape[:2]
    cv2.putText(frame, f"TARAMA — adim {step}/8", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,200,255), 2)
    cv2.putText(frame, "Ates bulunamadi, donuyor...", (10, 58),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (100,100,255), 1)


def draw_alert_banner(frame):
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, h//2-50), (w, h//2+50), (0,180,0), -1)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)
    cv2.putText(frame, "ATES ORTALANDI!", (w//2-200, h//2+15),
                cv2.FONT_HERSHEY_DUPLEX, 1.2, (255,255,255), 3)


# ── Tarama adımı ──────────────────────────────────────────────────────────────

def scan_step(ser, cap, model, conf_thresh: float, show_gui: bool, step: int):
    """
    45° dön → 500ms bekle → görüntüyü kontrol et.
    Ateş bulunursa (x1,y1,x2,y2,conf) döndürür, yoksa None.
    """
    log(f"[TARAMA] Adım {step}/8 — 45° sağa dönülüyor ({SCAN_TURN_MS}ms)")
    send_cmd(ser, "TURN_R")
    time.sleep(SCAN_TURN_MS / 1000.0)
    send_cmd(ser, "STOP")

    log(f"[TARAMA] Bekleniyor ({SCAN_WAIT_MS}ms)…")
    time.sleep(SCAN_WAIT_MS / 1000.0)

    ok, frame = cap.read()
    if not ok:
        return None, None

    detection = detect_fire(model, frame, conf_thresh)

    if show_gui:
        display = frame.copy()
        if detection:
            x1,y1,x2,y2,conf = detection
            cv2.rectangle(display, (x1,y1), (x2,y2), (0,80,255), 2)
            cv2.putText(display, f"ATES BULUNDU! {conf:.2f}", (x1, max(18,y1-6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,80,255), 2)
        else:
            draw_scan_hud(display, step)
        cv2.imshow("Fire Centering — Visual Servoing", display)
        cv2.waitKey(1)

    return detection, frame


# ── Ana döngü ─────────────────────────────────────────────────────────────────

def main():
    args = parse_args()
    log("[BAŞLANGIÇ] Kod 1 — Visual Servoing")

    ser = open_serial(args.port)

    try:
        local_path = Path(args.model_path).expanduser().resolve()
        model_path = ensure_local_model(
            args.hf_repo, args.hf_file, args.hf_cache_dir, local_path)
    except Exception as exc:
        log(f"[HATA] Model: {exc}")
        ser.close()
        raise

    model = YOLO(str(model_path))
    log(f"[MODEL] Yüklendi: {model_path}")

    cap = cv2.VideoCapture(to_source(args.source))
    if not cap.isOpened():
        ser.close()
        raise RuntimeError(f"Kamera açılamadı: {args.source}")
    log(f"[KAMERA] Açıldı: {args.source}")

    show_gui = not args.no_gui
    conf_thresh = max(args.conf, MIN_CONF)

    # Durum
    centered_since : float = 0.0
    alert_fired    : bool  = False
    last_direction : str   = ""
    last_cmd_time  : float = 0.0
    scan_step_idx  : int   = 0
    mode           : str   = "TARAMA"   # "TARAMA" | "ORTALAMA"

    try:
        while True:
            now = time.time()

            # ── TARAMA modu ───────────────────────────────────────────────────
            if mode == "TARAMA":
                scan_step_idx = (scan_step_idx % 8) + 1
                detection, frame = scan_step(
                    ser, cap, model, conf_thresh, show_gui, scan_step_idx)

                if frame is None:
                    log("[BİTİŞ] Kamera akışı sona erdi.")
                    break

                if detection is not None:
                    log("[GEÇIŞ] Ateş bulundu → ORTALAMA moduna geçiliyor")
                    mode = "ORTALAMA"
                    centered_since = 0.0
                    alert_fired    = False
                    last_direction = ""

                if show_gui and (cv2.waitKey(1) & 0xFF == ord("q")):
                    break
                continue

            # ── ORTALAMA modu (visual servoing) ───────────────────────────────
            ok, frame = cap.read()
            if not ok:
                log("[BİTİŞ] Kamera akışı sona erdi.")
                break

            fw = frame.shape[1]
            detection = detect_fire(model, frame, conf_thresh)

            if detection is None:
                # Ateş kayboldu → taramaya dön
                if last_direction != "":
                    send_cmd(ser, "STOP")
                log("[GEÇIŞ] Ateş kaybedildi → TARAMA moduna geçiliyor")
                mode           = "TARAMA"
                centered_since = 0.0
                alert_fired    = False
                last_direction = ""
                if show_gui:
                    cv2.imshow("Fire Centering — Visual Servoing", frame)
                    cv2.waitKey(1)
                continue

            x1, y1, x2, y2, conf = detection
            fire_cx = (x1 + x2) // 2
            fire_cy = (y1 + y2) // 2
            direction = get_direction(fire_cx, fw)

            if direction != last_direction:
                log(f"[KOMUT] {direction}  (cx={fire_cx}, hata={fire_cx - fw//2:+d}px)")
                last_direction = direction

            # Komut gönder
            if now - last_cmd_time >= CMD_INTERVAL:
                send_cmd(ser, direction if direction != "CENTERED" else "STOP")
                last_cmd_time = now

            # Centered sayacı
            if direction == "CENTERED":
                if centered_since == 0.0:
                    centered_since = now
                    log("[DURUM] Dead-zone'a girildi, sayaç başladı…")
                if now - centered_since >= CENTERED_HOLD and not alert_fired:
                    log("=" * 55)
                    log("  [ALERT] ATES ORTALANDI — flame sensör onayı bekleniyor")
                    log("=" * 55)
                    alert_fired = True
            else:
                if centered_since != 0.0:
                    log("[DURUM] Dead-zone'dan çıkıldı, sayaç sıfırlandı.")
                centered_since = 0.0
                alert_fired    = False

            if show_gui:
                draw_hud(frame, fire_cx, fire_cy, x1, y1, x2, y2,
                         direction, conf, centered_since, now, mode)
                if alert_fired:
                    draw_alert_banner(frame)
                cv2.imshow("Fire Centering — Visual Servoing", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    log("[ÇIKIŞ] 'q' basıldı.")
                    break

    except KeyboardInterrupt:
        log("[ÇIKIŞ] Ctrl+C")
    finally:
        send_cmd(ser, "STOP")
        log("[SERIAL] STOP gönderildi, port kapatılıyor.")
        ser.close()
        cap.release()
        cv2.destroyAllWindows()
        log("[BİTİŞ] Kaynaklar serbest bırakıldı.")


if __name__ == "__main__":
    main()