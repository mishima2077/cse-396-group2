// ===== SkidSteerMotors.h =====
#ifndef SKID_STEER_MOTORS_H
#define SKID_STEER_MOTORS_H

#include <Arduino.h>
#include "Config.h"

class SkidSteerMotors {
public:
  void begin();
  void drive(int leftSpeed, int rightSpeed);   // -255..255 (işaret = yön)
  void forward(uint8_t s = SPEED_CRUISE);
  void reverse(uint8_t s = SPEED_REVERSE);
  void stop();
  void pointTurnLeft(uint8_t s = SPEED_TURN);
  void pointTurnRight(uint8_t s = SPEED_TURN);
private:
  void setSide(uint8_t lpwm, uint8_t rpwm, int speed);
};

#endif