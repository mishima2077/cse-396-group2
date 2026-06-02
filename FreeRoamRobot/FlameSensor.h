// ===== FlameSensor.h =====
#ifndef FLAME_SENSOR_H
#define FLAME_SENSOR_H

#include <Arduino.h>
#include "Config.h"

// Flame sensor: AO analog ölçüm, DO dijital eşik çıkışı (LOW = ateş var).
class FlameSensor {
public:
  void begin() {
    pinMode(PIN_FLAME_AO, INPUT);
    pinMode(PIN_FLAME_DO, INPUT);
  }
  uint16_t raw()           const { return analogRead(PIN_FLAME_AO); }
  bool     flameDetected() const { return digitalRead(PIN_FLAME_DO) == LOW; }
};

#endif