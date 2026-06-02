"""
Arduino ↔ Pi serial iletişimi — düşük seviye.

Pi → Arduino: metin komutları  (FORWARD,160 / TURN_LEFT,200 / STOP / PUMP_ON …)
Arduino → Pi: sensör raporları (SONAR,L,C,R  /  FLAME,raw)
"""
from .config import log


def send(ser, cmd: str) -> None:
    """Arduino'ya tek satır komut gönder."""
    ser.write((cmd + "\n").encode())
    log(f"[CMD] -> {cmd}")


def send_once(ser, ms: dict, cmd: str) -> None:
    """Hareket komutunu sadece değişince gönder. STOP/PUMP için send() kullan."""
    if ms.get("last_cmd") == cmd:
        return
    send(ser, cmd)
    ms["last_cmd"] = cmd


def read_arduino(ser, ms: dict) -> None:
    """
    Serial buffer'ı non-blocking boşalt.
    SONAR ve FLAME satırlarını ms (mission state) sözlüğüne yazar.
    """
    while ser.in_waiting > 0:
        try:
            raw = ser.readline().decode("ascii", errors="ignore").strip()
            if raw.startswith("SONAR,"):
                parts = raw.split(",")
                if len(parts) == 4:
                    ms["sonar_L"] = int(parts[1])
                    ms["sonar_C"] = int(parts[2])
                    ms["sonar_R"] = int(parts[3])
            elif raw.startswith("FLAME,"):
                parts = raw.split(",")
                if len(parts) == 2:
                    ms["flame"] = int(parts[1])
        except Exception:
            pass
