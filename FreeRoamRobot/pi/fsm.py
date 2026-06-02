"""
Pi-side durum makineleri.

  free_roam()    — sonar verisine göre engel kaçınma (Config.h flowchart ile birebir)
  fire_mission() — AIMING → APPROACHING → SPRAYING → back_to_roam()

Her ikisi de CMD_INTERVAL_S aralıklı (arduino_controller.py'den) çağrılır.
"""
from .config import (
    log,
    ARDUINO_IMG_WIDTH, IMG_CENTER_PX, AIM_DEADBAND_PX,
    FIRE_STOP_CM, FLAME_THRESHOLD_PI, FLAME_CLEAR_S,
    WARNING_ZONE_CM, OBSERVE_WINDOW_S,
    TURN_370_S, TURN_90_S, TURN_180_S, REVERSE_S,
    SPEED_CRUISE, SPEED_TURN, SPEED_REVERSE, SPEED_APPROACH,
)
from .serial_bridge import send, send_once

# ---- Üst mod -----------------------------------------------------------------------
MODE_ROAM = "ROAM"
MODE_FIRE = "FIRE"

# ---- Free roam state'leri (Config.h RoamState ile eşleşmeli) ----------------------
R_STRAIGHT = "DRIVE_STRAIGHT"
R_TURN_370 = "TURN_370"
R_TURN_R90 = "TURN_RIGHT_90"
R_TURN_L90 = "TURN_LEFT_90"
R_TURN_180 = "TURN_180_BACK"

# ---- Ateş misyonu state'leri -------------------------------------------------------
M_AIMING      = "AIMING"
M_APPROACHING = "APPROACHING"
M_SPRAYING    = "SPRAYING"


def initial_state(now: float) -> dict:
    """Sıfırdan başlayan mission state sözlüğü."""
    return {
        "mode":          MODE_ROAM,
        # free roam
        "roam_state":    R_STRAIGHT,
        "roam_ts":       now,
        "roam_rev_done": False,
        # ateş misyonu
        "fire_state":    M_AIMING,
        "flame_clear_t": None,
        # sensör (Arduino'dan gelir)
        "sonar_L": 9999,
        "sonar_C": 9999,
        "sonar_R": 9999,
        "flame":   1023,
        # son gönderilen hareket komutu (send_once için)
        "last_cmd": "",
    }


def back_to_roam(ms: dict, now: float) -> None:
    """Her state'ten free-roam'a temiz geçiş."""
    ms["mode"]          = MODE_ROAM
    ms["fire_state"]    = M_AIMING
    ms["flame_clear_t"] = None
    ms["roam_state"]    = R_STRAIGHT
    ms["roam_ts"]       = now
    ms["roam_rev_done"] = False


# ---- Ateş Misyonu FSM --------------------------------------------------------------

def fire_mission(ser, ms: dict, tracks: dict, now: float, frame_width: int) -> None:
    """
    AIMING   : ateşi yatayda ortala (kamera cx hatasına göre döndür)
    APPROACHING: ortalıyken yaklaş; sonar_C ≤ FIRE_STOP_CM → SPRAYING
    SPRAYING : pompa açık; flame FLAME_CLEAR_S boyunca temizse söndü → ROAM
    """
    # Kameradan en iyi alerted track → normalize cx (0..639)
    alerted = [tr for tr in tracks.values() if tr["alerted"]]
    fire_cx = None
    if alerted:
        best    = min(alerted, key=lambda t: abs(t["cx"] - frame_width // 2))
        fire_cx = int(best["cx"] * (ARDUINO_IMG_WIDTH - 1) / max(frame_width - 1, 1))
        fire_cx = max(0, min(ARDUINO_IMG_WIDTH - 1, fire_cx))

    state = ms["fire_state"]

    if state == M_AIMING:
        if fire_cx is None:
            send(ser, "STOP")
            back_to_roam(ms, now)
            log("[MISSION] AIMING: ateş kayboldu → ROAM")
            return
        err = fire_cx - IMG_CENTER_PX
        if abs(err) <= AIM_DEADBAND_PX:
            send_once(ser, ms, f"FORWARD,{SPEED_APPROACH}")
            ms["fire_state"] = M_APPROACHING
            log("[MISSION] AIMING → APPROACHING")
        elif err > 0:
            send_once(ser, ms, f"TURN_RIGHT,{SPEED_APPROACH}")
        else:
            send_once(ser, ms, f"TURN_LEFT,{SPEED_APPROACH}")

    elif state == M_APPROACHING:
        if fire_cx is None:
            send(ser, "STOP")
            back_to_roam(ms, now)
            log("[MISSION] APPROACHING: ateş kayboldu → ROAM")
            return
        err = fire_cx - IMG_CENTER_PX
        if abs(err) > AIM_DEADBAND_PX:
            send(ser, "STOP")
            ms["fire_state"] = M_AIMING
            log(f"[MISSION] APPROACHING → AIMING (kayma {err}px)")
            return
        if ms["sonar_C"] <= FIRE_STOP_CM:
            send(ser, "STOP")
            send(ser, "PUMP_ON")
            ms["fire_state"]    = M_SPRAYING
            ms["flame_clear_t"] = None
            log(f"[MISSION] APPROACHING → SPRAYING dist={ms['sonar_C']}cm")
        else:
            send_once(ser, ms, f"FORWARD,{SPEED_APPROACH}")

    elif state == M_SPRAYING:
        if ms["flame"] < FLAME_THRESHOLD_PI:
            ms["flame_clear_t"] = None          # hâlâ ateş var
        else:
            if ms["flame_clear_t"] is None:
                ms["flame_clear_t"] = now       # temizlik sayacı başlat
            elif now - ms["flame_clear_t"] >= FLAME_CLEAR_S:
                send(ser, "PUMP_OFF")
                back_to_roam(ms, now)
                log("[MISSION] SPRAYING → ROAM ateş söndü")


# ---- Free Roam FSM -----------------------------------------------------------------

def free_roam(ser, ms: dict, now: float) -> None:
    """
    Arduino sonar verisine göre engel kaçınma.
    DRIVE_STRAIGHT → TURN_370 / TURN_RIGHT_90 / TURN_LEFT_90 / TURN_180_BACK
    """
    L = ms["sonar_L"]
    C = ms["sonar_C"]
    R = ms["sonar_R"]
    state   = ms["roam_state"]
    elapsed = now - ms["roam_ts"]

    def enter(s: str) -> None:
        ms["roam_state"]    = s
        ms["roam_ts"]       = now
        ms["roam_rev_done"] = False

    if state == R_STRAIGHT:
        send_once(ser, ms, f"FORWARD,{SPEED_CRUISE}")
        if C < WARNING_ZONE_CM:
            if   R >= WARNING_ZONE_CM: enter(R_TURN_R90)
            elif L >= WARNING_ZONE_CM: enter(R_TURN_L90)
            else:                      enter(R_TURN_180)
        elif elapsed >= OBSERVE_WINDOW_S:
            enter(R_TURN_370)

    elif state == R_TURN_370:
        send_once(ser, ms, f"TURN_RIGHT,{SPEED_TURN}")
        if elapsed >= TURN_370_S:
            enter(R_STRAIGHT)

    elif state == R_TURN_R90:
        send_once(ser, ms, f"TURN_RIGHT,{SPEED_TURN}")
        if elapsed >= TURN_90_S:
            enter(R_STRAIGHT)

    elif state == R_TURN_L90:
        send_once(ser, ms, f"TURN_LEFT,{SPEED_TURN}")
        if elapsed >= TURN_90_S:
            enter(R_STRAIGHT)

    elif state == R_TURN_180:
        if not ms["roam_rev_done"]:
            send_once(ser, ms, f"REVERSE,{SPEED_REVERSE}")
            if elapsed >= REVERSE_S:
                ms["roam_rev_done"] = True
                ms["roam_ts"]       = now      # geri bitti, dönüş sayacı başlat
        else:
            send_once(ser, ms, f"TURN_LEFT,{SPEED_TURN}")
            if elapsed >= TURN_180_S:
                enter(R_STRAIGHT)
