#!/usr/bin/env python3
"""
Kod 2 — Açı hesaplamalı ateş ortalama.

Davranış:
  - Ateş yok  → 45° adımlarla kendi etrafında tara (her adımda 500ms bekle)
  - Ateş var  → ateşin piksel offsetinden kaç derece dönmesi gerektiğini hesapla,
                o süre kadar dön, dur, tekrar kontrol et, ortalanınca tamamen dur.

Sabitler:
  360° = 4800ms  →  1° = 13.33ms
  MOTOR_SPEED = 255  (Config.h'de)
  DEAD_ZONE_DEG = 3°

Requirements:
  pip install ultralytics opencv-python huggingface_hub pyserial

Usage:
  python fire_centering_angle.py --source 0 --port /dev/ttyUSB0
"""

import argparse
import os
import time
from pathlib import Path

import cv2
import serial
import serial.tools.list_ports
from ultralytics import YOLO

# ── Model ─────────────────────────────────────────────────────────────────────
DEFAULT_HF_REPO     = "SalahALHaismawi/yolov26-fire-detection"
DEFAULT_HF_FILE     = "best.pt"
DEFAULT_LOCAL_MODEL = Path(__file__).resolve().parent / "models" / "best.pt"

# ── Algılama ──────────────────────────────────────────────────────────────────
MIN_CONF        = 0.40   # düşürüldü: 0.60 → 0.40, daha hassas tespit için
DETECT_FRAMES   = 3      # kaç frame üst üste tespit edilirse gerçek ateş sayılır

# ── Açı hesabı ────────────────────────────────────────────────────────────────
CAMERA_FOV_DEG  = 55.0
MS_PER_DEGREE   = 13.33
DEAD_ZONE_DEG   = 3.0
CENTERED_HOLD   = 1.5    # saniye — bu kadar stabil kalırsa alert
MAX_TURN_DEG    = 45.0   # tek seferde max dönüş

# ── Tarama ────────────────────────────────────────────────────────────────────
SCAN_TURN_MS    = 600    # 45° dönüş süresi
SCAN_WAIT_MS    = 500    # dönüş sonrası bekleme
BUFFER_FLUSH    = 3      # tarama sonrası buffer temizlemek için atılacak frame sayısı

# ── Dönüş sonrası bekleme ─────────────────────────────────────────────────────
POST_TURN_WAIT  = 0.5    # saniye — görüntünün stabilleşmesi için

# ── Serial ────────────────────────────────────────────────────────────────────
SERIAL_BAUD     = 115200


def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


def parse_args():
    parser = argparse.ArgumentParser(description="Kod 2 — Açı Hesaplamalı")
    parser.add_argument("--hf-repo",      default=DEFAULT_HF_REPO)
    parser.add_argument("--hf-file",      default=DEFAULT_HF_FILE)
    parser.add_argument("--hf-cache-dir", default=str(Path.home() / ".cache" / "fire-smoke-models"))
    parser.add_argument("--model-path",   default=str(DEFAULT_LOCAL_MODEL))
    parser.add_argument("--source",       default="0")
    parser.add_argument("--conf",         type=float, default=0.40)
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


def flush_camera(cap, n: int = BUFFER_FLUSH):
    """Kamera buffer'ındaki eski frame'leri at, taze frame al."""
    for _ in range(n):
        cap.read()


def detect_fire(model, frame, conf_thresh: float):
    """En yüksek güvenli 'fire' tespitini döndürür. Yoksa None."""
    results = model.predict(source=frame, conf=conf_thresh, verbose=False)
    best = None
    for r in results:
        for b in r.boxes or []:
            cls_id = int(b.cls[0].item())
            conf   = float(b.conf[0].item())
            label  = str(r.names.get(cls_id, cls_id)).lower()
            if label != "fire" or conf < conf_thresh:
                continue
            x1, y1, x2, y2 = map(int, b.xyxy[0].tolist())
            if best is None or conf > best[4]:
                best = (x1, y1, x2, y2, conf)
    return best


def px_to_degrees(error_px: int, frame_width: int) -> float:
    """Piksel offsetini dereceye çevirir. + sağ, - sol."""
    return error_px / (frame_width / CAMERA_FOV_DEG)


def turn_by_degrees(ser, degrees: float):
    """Hesaplanan açı kadar döner, STOP gönderir, stabilleşme için bekler."""
    clamped = max(-MAX_TURN_DEG, min(MAX_TURN_DEG, degrees))
    if abs(round(clamped, 2)) != abs(round(degrees, 2)):
        log(f"[UYARI] Açı {degrees:.1f}° → {clamped:.1f}°'ye sınırlandı")

    turn_ms   = abs(clamped) * MS_PER_DEGREE
    direction = "TURN_R" if clamped > 0 else "TURN_L"

    log(f"[DONUS] {direction}  {abs(clamped):.1f}°  ({turn_ms:.0f}ms)")
    send_cmd(ser, direction)
    time.sleep(turn_ms / 1000.0)
    send_cmd(ser, "STOP")          # ← dönüş bitti, motor dur
    time.sleep(POST_TURN_WAIT)     # görüntü stabilleşsin


# ── HUD ───────────────────────────────────────────────────────────────────────

def draw_hud(frame, fire_cx, fire_cy, x1, y1, x2, y2,
             conf, error_deg, is_centered, centered_since, now, mode):
    h, w = frame.shape[:2]
    cx_frame = w // 2

    for y in range(0, h, 20):
        cv2.line(frame, (cx_frame, y), (cx_frame, min(y+10, h)), (200,200,200), 1)

    dz_px = int(DEAD_ZONE_DEG * (w / CAMERA_FOV_DEG))
    cv2.line(frame, (cx_frame-dz_px, 0), (cx_frame-dz_px, h), (0,200,255), 1)
    cv2.line(frame, (cx_frame+dz_px, 0), (cx_frame+dz_px, h), (0,200,255), 1)

    cv2.putText(frame, f"MOD: {mode}", (w-200, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,0), 2)

    box_color = (0,255,0) if is_centered else (0,80,255)
    cv2.rectangle(frame, (x1,y1), (x2,y2), box_color, 2)
    cv2.putText(frame, f"fire {conf:.2f}", (x1, max(18, y1-6)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, box_color, 2)

    cv2.circle(frame, (fire_cx, fire_cy), 5, (0,255,255), -1)
    cv2.arrowedLine(frame, (fire_cx, fire_cy), (cx_frame, fire_cy),
                    (0,255,255), 2, tipLength=0.2)

    if is_centered:
        hold = now - centered_since if centered_since else 0.0
        remaining = max(0.0, CENTERED_HOLD - hold)
        label = f"CENTERED ({remaining:.1f}s)" if remaining > 0 else "CENTERED"
        color = (0,255,0)
    else:
        d = "SAG" if error_deg > 0 else "SOL"
        label = f"{d} DON: {abs(error_deg):.1f} derece"
        color = (0,80,255)

    cv2.putText(frame, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
    cv2.putText(frame, f"hata: {error_deg:+.1f} derece", (10, 58),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200,200,200), 1)


def draw_scan_hud(frame, step):
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

def scan_step(ser, cap, model, conf_thresh, show_gui, step):
    """45° dön → dur → buffer temizle → taze frame al → tespit et."""
    log(f"[TARAMA] Adım {step}/8 — 45° sağa ({SCAN_TURN_MS}ms)")
    send_cmd(ser, "TURN_R")
    time.sleep(SCAN_TURN_MS / 1000.0)
    send_cmd(ser, "STOP")

    log(f"[TARAMA] Bekleniyor ({SCAN_WAIT_MS}ms)…")
    time.sleep(SCAN_WAIT_MS / 1000.0)

    # Buffer'daki eski frame'leri temizle, taze frame al
    flush_camera(cap)
    ok, frame = cap.read()
    if not ok:
        return None, None

    detection = detect_fire(model, frame, conf_thresh)

    if show_gui:
        display = frame.copy()
        if detection:
            x1,y1,x2,y2,conf = detection
            cv2.rectangle(display, (x1,y1), (x2,y2), (0,80,255), 2)
            cv2.putText(display, f"ATES BULUNDU! {conf:.2f}",
                        (x1, max(18,y1-6)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,80,255), 2)
        else:
            draw_scan_hud(display, step)
        cv2.imshow("Fire Centering — Aci Hesaplama", display)
        cv2.waitKey(1)

    return detection, frame


# ── Ana döngü ─────────────────────────────────────────────────────────────────

def main():
    args = parse_args()
    log("[BAŞLANGIÇ] Kod 2 — Açı Hesaplamalı")

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

    show_gui    = not args.no_gui
    conf_thresh = max(args.conf, MIN_CONF)
    log(f"[AYAR] conf_thresh={conf_thresh}, dead_zone=±{DEAD_ZONE_DEG}°")

    # Durum
    centered_since  : float = 0.0
    alert_fired     : bool  = False
    scan_step_idx   : int   = 0
    mode            : str   = "TARAMA"
    consec_centered : int   = 0   # üst üste kaç frame centered geldi

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
                    x1,y1,x2,y2,conf = detection
                    log(f"[GEÇIŞ] Ateş bulundu (conf={conf:.2f}) → ORTALAMA moduna geçiliyor")
                    mode            = "ORTALAMA"
                    centered_since  = 0.0
                    alert_fired     = False
                    consec_centered = 0

                if show_gui and (cv2.waitKey(1) & 0xFF == ord("q")):
                    break
                continue

            # ── ORTALAMA modu ─────────────────────────────────────────────────

            # Taze frame al (buffer temizle)
            flush_camera(cap, 2)
            ok, frame = cap.read()
            if not ok:
                log("[BİTİŞ] Kamera akışı sona erdi.")
                break

            fw = frame.shape[1]
            detection = detect_fire(model, frame, conf_thresh)

            if detection is None:
                log("[GEÇIŞ] Ateş kaybedildi → TARAMA moduna geçiliyor")
                send_cmd(ser, "STOP")   # güvenlik için dur
                mode            = "TARAMA"
                centered_since  = 0.0
                alert_fired     = False
                consec_centered = 0
                if show_gui:
                    cv2.imshow("Fire Centering — Aci Hesaplama", frame)
                    cv2.waitKey(1)
                continue

            x1, y1, x2, y2, conf = detection
            fire_cx   = (x1 + x2) // 2
            fire_cy   = (y1 + y2) // 2
            error_px  = fire_cx - fw // 2
            error_deg = px_to_degrees(error_px, fw)
            is_centered = abs(error_deg) <= DEAD_ZONE_DEG

            log(f"[ÖLÇÜM] cx={fire_cx}  hata={error_deg:+.1f}°  conf={conf:.2f}  centered={is_centered}")

            if is_centered:
                # ── Ortalandı: motor zaten duruyor, sayacı işlet ─────────────
                consec_centered += 1
                if centered_since == 0.0:
                    centered_since = now
                    log(f"[DURUM] Dead-zone'a girildi (±{DEAD_ZONE_DEG}°), sayaç başladı…")

                # Ekranı güncelle
                if show_gui:
                    draw_hud(frame, fire_cx, fire_cy, x1, y1, x2, y2,
                             conf, error_deg, True, centered_since, now, mode)
                    if now - centered_since >= CENTERED_HOLD:
                        draw_alert_banner(frame)
                    cv2.imshow("Fire Centering — Aci Hesaplama", frame)
                    cv2.waitKey(1)

                if now - centered_since >= CENTERED_HOLD and not alert_fired:
                    log("=" * 55)
                    log("  [ALERT] ATES ORTALANDI — flame sensör onayı bekleniyor")
                    log("=" * 55)
                    alert_fired = True
                    # Ortalandı: motor zaten durmuş durumda, burada bekle
                    # (bir sonraki adım: flame sensör entegrasyonu)

            else:
                # ── Dead zone dışında: dön ve tekrar ölç ─────────────────────
                if centered_since != 0.0:
                    log("[DURUM] Dead-zone'dan çıkıldı, sayaç sıfırlandı.")
                centered_since  = 0.0
                alert_fired     = False
                consec_centered = 0

                if show_gui:
                    draw_hud(frame, fire_cx, fire_cy, x1, y1, x2, y2,
                             conf, error_deg, False, 0.0, now, mode)
                    cv2.imshow("Fire Centering — Aci Hesaplama", frame)
                    cv2.waitKey(1)

                # Dön — turn_by_degrees içinde STOP zaten gönderiliyor
                turn_by_degrees(ser, error_deg)
                # Dönüş sonrası buffer'ı temizle
                flush_camera(cap)

            if show_gui and (cv2.waitKey(1) & 0xFF == ord("q")):
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