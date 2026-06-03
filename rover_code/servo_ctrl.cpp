#include <Arduino.h>
#include <Servo.h>
#include "servo_ctrl.h"
#include "Config.h"

static Servo s_servo;
static uint8_t s_angle = 90;

void servo_init(void) {
    s_servo.attach(PIN_SERVO);
    servo_set(90);
}

void servo_set(uint8_t angle) {
    s_angle = constrain(angle, 0, 180);
    s_servo.write(s_angle);
}

uint8_t servo_get(void) {
    return s_angle;
}
