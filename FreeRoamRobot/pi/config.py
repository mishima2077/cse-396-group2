"""
Tüm sabitler — Config.h ile eşleşmeli.
Değer değişirse burası güncellenir, diğer modüller dokunulmaz.
"""
import time

# ---- Görüntü / algılama ------------------------------------------------------------
MIN_ALERT_CONF    = 0.60
ARDUINO_IMG_WIDTH = 640   # Arduino'nun beklediği normalize genişlik

# ---- Ateş misyonu ------------------------------------------------------------------
FIRE_STOP_CM       = 30   # bu mesafede dur, pompa aç
AIM_DEADBAND_PX    = 40   # |hata| < bu → ortalandı say
IMG_CENTER_PX      = 320  # 640px görüntünün merkezi
FLAME_THRESHOLD_PI = 300  # analogRead < eşik → ateş var
FLAME_CLEAR_S      = 3.0  # flame bu kadar temizse söndü say

# ---- Free roam ---------------------------------------------------------------------
WARNING_ZONE_CM  = 35
OBSERVE_WINDOW_S = 15.0   # bu süre engel yoksa 370° dön
TURN_370_S       = 2.6
TURN_90_S        = 0.6
TURN_180_S       = 1.2
REVERSE_S        = 0.7

# ---- Motor hızları (0-255) ---------------------------------------------------------
SPEED_CRUISE   = 180
SPEED_TURN     = 200
SPEED_REVERSE  = 170
SPEED_APPROACH = 160

# ---- Arduino iletişim --------------------------------------------------------------
CMD_INTERVAL_S = 0.1   # Arduino komut döngüsü (10 Hz)


def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")
