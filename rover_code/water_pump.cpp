#include <Arduino.h>
#include "water_pump.h"

void pump_init(void) {
    pinMode(PUMP_SIG_PIN, OUTPUT);
    digitalWrite(PUMP_SIG_PIN, LOW);
}

void pump_start(void) {
    digitalWrite(PUMP_SIG_PIN, HIGH);
}

void pump_stop(void) {
    digitalWrite(PUMP_SIG_PIN, LOW);
}
