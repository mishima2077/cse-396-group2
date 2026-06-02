// ===== WaterPump.h =====
#ifndef WATER_PUMP_H
#define WATER_PUMP_H

#include <Arduino.h>
#include "Config.h"

// R385 pompa, tek dijital pinle MOSFET/röle üzerinden tetiklenir.
class WaterPump {
public:
  void begin() { pinMode(PIN_WATER_PUMP, OUTPUT); off(); }
  void on()    { digitalWrite(PIN_WATER_PUMP, HIGH); }
  void off()   { digitalWrite(PIN_WATER_PUMP, LOW);  }
};

#endif