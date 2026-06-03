#include <Arduino.h>
#include "water_pump.h"

static bool pump_running = false;

void pump_init(void) {
    pinMode(PIN_WATER_PUMP, OUTPUT);
    digitalWrite(PIN_WATER_PUMP, LOW);
    pump_running = false;
}

void pump_on(void) {
    digitalWrite(PIN_WATER_PUMP, HIGH);
    pump_running = true;
}

void pump_off(void) {
    digitalWrite(PIN_WATER_PUMP, LOW);
    pump_running = false;
}

bool pump_is_on(void) {
    return pump_running;
}
