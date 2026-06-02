// ===== TripleSonarArray.h =====
#ifndef TRIPLE_SONAR_ARRAY_H
#define TRIPLE_SONAR_ARRAY_H

#include <Arduino.h>
#include "Config.h"

class TripleSonarArray {
public:
  enum Index : uint8_t { LEFT = 0, CENTER = 1, RIGHT = 2, COUNT = 3 };
  void begin();
  void update();
  uint16_t left()   const { return distance_[LEFT];   }
  uint16_t center() const { return distance_[CENTER]; }
  uint16_t right()  const { return distance_[RIGHT];  }
private:
  enum Phase : uint8_t { TRIG_PREP, TRIG_PRELOW, TRIG_HIGH, WAIT_ECHO_HIGH, WAIT_ECHO_LOW, SETTLE };
  void beginSettle();
  uint8_t  trig_[COUNT], echo_[COUNT];
  uint16_t distance_[COUNT];
  uint8_t  cur_;
  Phase    phase_;
  unsigned long tMark_, echoStart_, tSettle_;
};

#endif