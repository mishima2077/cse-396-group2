#include <Arduino.h>
#include "flame.h"

static uint16_t last_analog = 0;
static uint8_t last_digital = 1;

void flame_init(void) {
    pinMode(PIN_FLAME_DO, INPUT);
    pinMode(PIN_FLAME_AO, INPUT);
}

void flame_update(void) {
    last_analog = (uint16_t)analogRead(PIN_FLAME_AO);
    last_digital = (digitalRead(PIN_FLAME_DO) == LOW) ? 0 : 1;
}

uint16_t flame_get_analog(void) {
    return last_analog;
}

uint8_t flame_get_digital(void) {
    return last_digital;
}
