"""
Arduino worker thread.

YOLO thread'den tamamen bağımsız çalışır (10 Hz sabit döngü).
Sonar/flame okur, FSM'i çalıştırır, Arduino'ya komut gönderir.

Paylaşılan veri:
  shared_tracks — tracks_lock altında okunur (YOLO thread yazar)
"""
import time

from .config import log, CMD_INTERVAL_S
from .serial_bridge import read_arduino
from .fsm import (
    initial_state,
    fire_mission, free_roam,
    MODE_ROAM, MODE_FIRE, M_AIMING,
)


def arduino_worker(ser, frame_width: int,
                   shared_tracks: dict, tracks_lock, stop_event) -> None:
    ms = initial_state(time.time())
    log("[ARDUINO] Thread hazır.")

    while not stop_event.is_set():
        t0  = time.time()
        now = t0

        # Sensörleri oku (non-blocking)
        read_arduino(ser, ms)

        # En güncel track snapshot (kısa lock)
        with tracks_lock:
            tracks = dict(shared_tracks)

        # Ateş algılandıysa misyona geç
        if any(tr["alerted"] for tr in tracks.values()) and ms["mode"] == MODE_ROAM:
            ms["mode"]       = MODE_FIRE
            ms["fire_state"] = M_AIMING
            log("[DISPATCH] ROAM → FIRE misyonu başladı")

        # FSM çalıştır
        if ms["mode"] == MODE_FIRE:
            fire_mission(ser, ms, tracks, now, frame_width)
        else:
            free_roam(ser, ms, now)

        # 10 Hz'i koru
        remaining = CMD_INTERVAL_S - (time.time() - t0)
        if remaining > 0:
            time.sleep(remaining)

    # Thread çıkışında güvenli durdur
    try:
        ser.write(b"PUMP_OFF\n")
        ser.write(b"STOP\n")
    except Exception:
        pass
    log("[ARDUINO] Thread sonlandı.")
