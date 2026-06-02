// ===== SkidSteerMotors.cpp =====
#include "SkidSteerMotors.h"

void SkidSteerMotors::begin() {
  pinMode(PIN_LEFT_LPWM,  OUTPUT); pinMode(PIN_LEFT_RPWM,  OUTPUT);
  pinMode(PIN_LEFT_LEN,   OUTPUT); pinMode(PIN_LEFT_REN,   OUTPUT);
  pinMode(PIN_RIGHT_LPWM, OUTPUT); pinMode(PIN_RIGHT_RPWM, OUTPUT);
  pinMode(PIN_RIGHT_LEN,  OUTPUT); pinMode(PIN_RIGHT_REN,  OUTPUT);
  // sürücüleri etkinleştir
  digitalWrite(PIN_LEFT_LEN,  HIGH); digitalWrite(PIN_LEFT_REN,  HIGH);
  digitalWrite(PIN_RIGHT_LEN, HIGH); digitalWrite(PIN_RIGHT_REN, HIGH);
  stop();
}
void SkidSteerMotors::drive(int l, int r) {
  setSide(PIN_LEFT_LPWM,  PIN_LEFT_RPWM,  l);
  setSide(PIN_RIGHT_LPWM, PIN_RIGHT_RPWM, r);
}
void SkidSteerMotors::forward(uint8_t s) { drive( (int)s,  (int)s); }
void SkidSteerMotors::reverse(uint8_t s) { drive(-(int)s, -(int)s); }
void SkidSteerMotors::stop()             { drive(0, 0); }
void SkidSteerMotors::pointTurnLeft(uint8_t s)  { drive(-(int)s,  (int)s); }
void SkidSteerMotors::pointTurnRight(uint8_t s) { drive( (int)s, -(int)s); }

void SkidSteerMotors::setSide(uint8_t lpwm, uint8_t rpwm, int speed) {
  int mag = speed < 0 ? -speed : speed;
  if (mag > 255) mag = 255;
  if (speed > 0) {
    analogWrite(lpwm, (uint8_t)mag);
    analogWrite(rpwm, 0);
  } else if (speed < 0) {
    analogWrite(lpwm, 0);
    analogWrite(rpwm, (uint8_t)mag);
  } else {
    analogWrite(lpwm, 0);
    analogWrite(rpwm, 0);
  }
}