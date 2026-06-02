"""
Unit testler: pi/serial_bridge.py :: read_arduino()

Arduino'dan gelen SONAR ve FLAME satırlarının doğru parse edildiğini doğrular.
Serial port gerçek donanım olmadan mock ile simüle edilir.

Çalıştır:
  python -m pytest tests/test_serial_bridge.py -v
  python -m unittest tests/test_serial_bridge -v   (pytest yoksa)
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, PropertyMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pi.serial_bridge import read_arduino


# ---------------------------------------------------------------------------
# Yardımcı: sahte serial port oluştur
# ---------------------------------------------------------------------------

def _make_ser(*lines: str):
    """
    lines: Arduino'nun göndereceği satırlar (str).
    in_waiting: her satır için 1, sonra 0 → döngü durur.
    """
    ser = MagicMock()
    type(ser).in_waiting = PropertyMock(side_effect=[1] * len(lines) + [0])
    ser.readline.side_effect = [line.encode() for line in lines]
    return ser


def _empty_state() -> dict:
    return {"sonar_L": 9999, "sonar_C": 9999, "sonar_R": 9999, "flame": 1023}


# ---------------------------------------------------------------------------
# SONAR testleri
# ---------------------------------------------------------------------------

class TestSonarParsing(unittest.TestCase):

    def test_three_sensors_parsed(self):
        """Normal SONAR satırı → 3 sensör değeri doğru okunur."""
        ms  = _empty_state()
        ser = _make_ser("SONAR,34,89,41\n")
        read_arduino(ser, ms)

        self.assertEqual(ms["sonar_L"], 34)
        self.assertEqual(ms["sonar_C"], 89)
        self.assertEqual(ms["sonar_R"], 41)

        print(f"\n  [SONAR] L={ms['sonar_L']}cm  C={ms['sonar_C']}cm  R={ms['sonar_R']}cm")

    def test_sensor_boundary_zero(self):
        """Sıfır mesafe değerleri kabul edilir."""
        ms  = _empty_state()
        ser = _make_ser("SONAR,0,0,0\n")
        read_arduino(ser, ms)

        self.assertEqual(ms["sonar_L"], 0)
        self.assertEqual(ms["sonar_C"], 0)
        self.assertEqual(ms["sonar_R"], 0)

        print(f"\n  [SONAR] L={ms['sonar_L']}cm  C={ms['sonar_C']}cm  R={ms['sonar_R']}cm")

    def test_sensor_max_distance(self):
        """340cm (SONAR_MAX_CM) değerleri kabul edilir."""
        ms  = _empty_state()
        ser = _make_ser("SONAR,340,340,340\n")
        read_arduino(ser, ms)

        self.assertEqual(ms["sonar_L"], 340)
        self.assertEqual(ms["sonar_C"], 340)
        self.assertEqual(ms["sonar_R"], 340)

        print(f"\n  [SONAR] L={ms['sonar_L']}cm  C={ms['sonar_C']}cm  R={ms['sonar_R']}cm")

    def test_missing_field_ignored(self):
        """Eksik alan → state değişmemeli."""
        ms  = _empty_state()
        ser = _make_ser("SONAR,10,20\n")   # R eksik
        read_arduino(ser, ms)

        self.assertEqual(ms["sonar_L"], 9999)
        self.assertEqual(ms["sonar_C"], 9999)
        self.assertEqual(ms["sonar_R"], 9999)

    def test_extra_whitespace_stripped(self):
        """Satır sonu boşlukları/CR parse'ı bozmaz."""
        ms  = _empty_state()
        ser = _make_ser("SONAR,12,25,18\r\n")
        read_arduino(ser, ms)

        self.assertEqual(ms["sonar_L"], 12)
        self.assertEqual(ms["sonar_C"], 25)
        self.assertEqual(ms["sonar_R"], 18)

        print(f"\n  [SONAR] L={ms['sonar_L']}cm  C={ms['sonar_C']}cm  R={ms['sonar_R']}cm")

    def test_asymmetric_readings(self):
        """Sol/merkez/sağ birbirinden farklı değerler."""
        ms  = _empty_state()
        ser = _make_ser("SONAR,15,340,8\n")
        read_arduino(ser, ms)

        self.assertEqual(ms["sonar_L"], 15)
        self.assertEqual(ms["sonar_C"], 340)
        self.assertEqual(ms["sonar_R"], 8)

        print(f"\n  [SONAR] L={ms['sonar_L']}cm  C={ms['sonar_C']}cm  R={ms['sonar_R']}cm")


# ---------------------------------------------------------------------------
# FLAME testleri
# ---------------------------------------------------------------------------

class TestFlameParsing(unittest.TestCase):

    def test_flame_no_fire(self):
        """Yüksek analogRead → ateş yok."""
        ms  = _empty_state()
        ser = _make_ser("FLAME,687\n")
        read_arduino(ser, ms)

        self.assertEqual(ms["flame"], 687)
        fire = ms["flame"] < 300
        print(f"\n  [FLAME] raw={ms['flame']}  ateş={'VAR' if fire else 'YOK'}")

    def test_flame_fire_detected(self):
        """Düşük analogRead (< 300) → ateş var."""
        ms  = _empty_state()
        ser = _make_ser("FLAME,120\n")
        read_arduino(ser, ms)

        self.assertEqual(ms["flame"], 120)
        fire = ms["flame"] < 300
        self.assertTrue(fire)
        print(f"\n  [FLAME] raw={ms['flame']}  ateş={'VAR' if fire else 'YOK'}")

    def test_flame_threshold_boundary(self):
        """Tam eşikte (300) ateş yok sayılır."""
        ms  = _empty_state()
        ser = _make_ser("FLAME,300\n")
        read_arduino(ser, ms)

        self.assertEqual(ms["flame"], 300)
        self.assertFalse(ms["flame"] < 300)


# ---------------------------------------------------------------------------
# Karma / hata tolerans testleri
# ---------------------------------------------------------------------------

class TestMixedAndErrorTolerance(unittest.TestCase):

    def test_sonar_then_flame(self):
        """Tek döngüde hem SONAR hem FLAME satırı."""
        ms  = _empty_state()
        ser = _make_ser("SONAR,10,20,30\n", "FLAME,150\n")
        read_arduino(ser, ms)

        self.assertEqual(ms["sonar_L"], 10)
        self.assertEqual(ms["sonar_C"], 20)
        self.assertEqual(ms["sonar_R"], 30)
        self.assertEqual(ms["flame"], 150)

        fire = ms["flame"] < 300
        print(
            f"\n  [SONAR] L={ms['sonar_L']}cm  C={ms['sonar_C']}cm  R={ms['sonar_R']}cm"
            f"\n  [FLAME] raw={ms['flame']}  ateş={'VAR' if fire else 'YOK'}"
        )

    def test_unknown_line_ignored(self):
        """Bilinmeyen satır state'i bozmaz."""
        ms  = _empty_state()
        ser = _make_ser("UNKNOWN,abc\n", "SONAR,5,10,15\n")
        read_arduino(ser, ms)

        self.assertEqual(ms["sonar_L"], 5)
        self.assertEqual(ms["sonar_C"], 10)
        self.assertEqual(ms["sonar_R"], 15)

    def test_corrupt_line_ignored(self):
        """Bozuk satır exception'a yol açmaz, state değişmez."""
        ms  = _empty_state()
        ser = _make_ser("SONAR,abc,def,ghi\n")
        read_arduino(ser, ms)

        self.assertEqual(ms["sonar_L"], 9999)   # değişmemiş

    def test_latest_sonar_wins(self):
        """Aynı döngüde iki SONAR satırı → sonuncusu geçerli."""
        ms  = _empty_state()
        ser = _make_ser("SONAR,1,2,3\n", "SONAR,100,200,300\n")
        read_arduino(ser, ms)

        self.assertEqual(ms["sonar_L"], 100)
        self.assertEqual(ms["sonar_C"], 200)
        self.assertEqual(ms["sonar_R"], 300)

        print(f"\n  [SONAR son] L={ms['sonar_L']}cm  C={ms['sonar_C']}cm  R={ms['sonar_R']}cm")


if __name__ == "__main__":
    unittest.main(verbosity=2)
