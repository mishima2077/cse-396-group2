#include <Arduino.h>
#include "distance.h"

void distance_init(void) {
    pinMode(DIST_TRIG_PIN, OUTPUT);
    pinMode(DIST_ECHO_PIN, INPUT);
    digitalWrite(DIST_TRIG_PIN, LOW);
}

uint16_t distance_read_cm(void) {
    digitalWrite(DIST_TRIG_PIN, LOW);
    delayMicroseconds(2);
    digitalWrite(DIST_TRIG_PIN, HIGH);
    delayMicroseconds(10);
    digitalWrite(DIST_TRIG_PIN, LOW);

    unsigned long duration = pulseIn(DIST_ECHO_PIN, HIGH, 30000UL);
    return (uint16_t)(duration / 58UL);
}
