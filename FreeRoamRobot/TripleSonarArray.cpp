// ===== TripleSonarArray.cpp =====
#include "TripleSonarArray.h"

void TripleSonarArray::begin() {
  trig_[LEFT]   = PIN_TRIG_LEFT;   echo_[LEFT]   = PIN_ECHO_LEFT;
  trig_[CENTER] = PIN_TRIG_CENTER; echo_[CENTER] = PIN_ECHO_CENTER;
  trig_[RIGHT]  = PIN_TRIG_RIGHT;  echo_[RIGHT]  = PIN_ECHO_RIGHT;
  for (uint8_t i = 0; i < COUNT; i++) {
    pinMode(trig_[i], OUTPUT); digitalWrite(trig_[i], LOW);
    pinMode(echo_[i], INPUT);
    distance_[i] = SONAR_MAX_CM;  // Pi başlangıçta max mesafe görür → ileri gider
  }
  cur_ = LEFT; phase_ = TRIG_PREP; tMark_ = micros();
}

void TripleSonarArray::update() {
  switch (phase_) {
    case TRIG_PREP:
      digitalWrite(trig_[cur_], LOW); tMark_ = micros(); phase_ = TRIG_PRELOW; break;
    case TRIG_PRELOW:
      if (micros() - tMark_ >= SONAR_TRIG_PRE_US) {
        digitalWrite(trig_[cur_], HIGH); tMark_ = micros(); phase_ = TRIG_HIGH;
      } break;
    case TRIG_HIGH:
      if (micros() - tMark_ >= SONAR_TRIG_US) {
        digitalWrite(trig_[cur_], LOW); tMark_ = micros(); phase_ = WAIT_ECHO_HIGH;
      } break;
    case WAIT_ECHO_HIGH:
      if (digitalRead(echo_[cur_]) == HIGH) { echoStart_ = micros(); phase_ = WAIT_ECHO_LOW; }
      else if (micros() - tMark_ >= SONAR_TIMEOUT_US) { distance_[cur_] = SONAR_MAX_CM; beginSettle(); }
      break;
    case WAIT_ECHO_LOW:
      if (digitalRead(echo_[cur_]) == LOW) {
        unsigned long dur = micros() - echoStart_;
        uint16_t cm = (uint16_t)(dur / 58UL);
        if (cm == 0) cm = 1; if (cm > SONAR_MAX_CM) cm = SONAR_MAX_CM;
        distance_[cur_] = cm; beginSettle();
      } else if (micros() - tMark_ >= SONAR_TIMEOUT_US) { distance_[cur_] = SONAR_MAX_CM; beginSettle(); }
      break;
    case SETTLE:
      if (millis() - tSettle_ >= SONAR_SETTLE_MS) { cur_ = (cur_ + 1) % COUNT; phase_ = TRIG_PREP; }
      break;
  }
}

void TripleSonarArray::beginSettle() { tSettle_ = millis(); phase_ = SETTLE; }