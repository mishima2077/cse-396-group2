#include <Arduino.h>
#include "flame.h"

static const uint8_t do_pins[FLAME_SENSOR_COUNT] = FLAME_DO_PINS;
static const uint8_t ao_pins[FLAME_SENSOR_COUNT] = FLAME_AO_PINS;

void flame_init(void) {
    for (uint8_t i = 0; i < FLAME_SENSOR_COUNT; i++) {
        pinMode(do_pins[i], INPUT);
        pinMode(ao_pins[i], INPUT);
    }
}

void flame_read(uint16_t *values) {
    for (uint8_t i = 0; i < FLAME_SENSOR_COUNT; i++) {
        values[i] = (uint16_t)analogRead(ao_pins[i]);
    }
}

void flame_detected(bool *results) {
    for (uint8_t i = 0; i < FLAME_SENSOR_COUNT; i++) {
        results[i] = digitalRead(do_pins[i]) == LOW;
    }
}
