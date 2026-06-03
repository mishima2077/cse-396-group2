#include <Arduino.h>
#include "distance.h"

struct Sensor {
    uint8_t trig_pin;
    uint8_t echo_pin;
    uint16_t last_reading;
};

static Sensor sensors[3] = {
    {PIN_TRIG_LEFT, PIN_ECHO_LEFT, 0},
    {PIN_TRIG_CENTER, PIN_ECHO_CENTER, 0},
    {PIN_TRIG_RIGHT, PIN_ECHO_RIGHT, 0}
};

static uint8_t current_sensor = 0;
static unsigned long last_trigger_time = 0;

void distance_init(void) {
    for (int i = 0; i < 3; i++) {
        pinMode(sensors[i].trig_pin, OUTPUT);
        pinMode(sensors[i].echo_pin, INPUT);
        digitalWrite(sensors[i].trig_pin, LOW);
    }
}

void distance_update(void) {
    unsigned long now = millis();

    // Trigger one sensor per cycle (round-robin, ~20ms per sensor)
    if (now - last_trigger_time >= 20UL) {
        last_trigger_time = now;

        Sensor& s = sensors[current_sensor];

        // Send trigger pulse (10µs)
        digitalWrite(s.trig_pin, LOW);
        delayMicroseconds(2);
        digitalWrite(s.trig_pin, HIGH);
        delayMicroseconds(10);
        digitalWrite(s.trig_pin, LOW);

        // Wait for echo (with timeout)
        unsigned long pulse_duration = pulseIn(s.echo_pin, HIGH, 24000UL);
        if (pulse_duration > 0) {
            s.last_reading = (uint16_t)(pulse_duration / 58UL);
        } else {
            s.last_reading = SONAR_MAX_CM;
        }

        // Move to next sensor
        current_sensor = (current_sensor + 1) % 3;
    }
}

uint16_t distance_get_left(void) {
    return sensors[0].last_reading;
}

uint16_t distance_get_center(void) {
    return sensors[1].last_reading;
}

uint16_t distance_get_right(void) {
    return sensors[2].last_reading;
}
