#include <Arduino.h>
#include "Motors.h"

void motors_init(void) {
    // Left motor pins
    pinMode(PIN_LEFT_RPWM, OUTPUT);
    pinMode(PIN_LEFT_LPWM, OUTPUT);
    pinMode(PIN_LEFT_REN, OUTPUT);
    pinMode(PIN_LEFT_LEN, OUTPUT);

    // Right motor pins
    pinMode(PIN_RIGHT_RPWM, OUTPUT);
    pinMode(PIN_RIGHT_LPWM, OUTPUT);
    pinMode(PIN_RIGHT_REN, OUTPUT);
    pinMode(PIN_RIGHT_LEN, OUTPUT);

    // Enable drivers
    digitalWrite(PIN_LEFT_REN, HIGH);
    digitalWrite(PIN_LEFT_LEN, HIGH);
    digitalWrite(PIN_RIGHT_REN, HIGH);
    digitalWrite(PIN_RIGHT_LEN, HIGH);

    stop();
}

void left_forward(uint8_t speed) {
    uint8_t s = constrain(speed, 0, 255);
    analogWrite(PIN_LEFT_RPWM, s);
    analogWrite(PIN_LEFT_LPWM, 0);
}

void left_reverse(uint8_t speed) {
    uint8_t s = constrain(speed, 0, 255);
    analogWrite(PIN_LEFT_RPWM, 0);
    analogWrite(PIN_LEFT_LPWM, s);
}

void right_forward(uint8_t speed) {
    uint8_t s = constrain(speed, 0, 255);
    analogWrite(PIN_RIGHT_RPWM, 0);
    analogWrite(PIN_RIGHT_LPWM, s);
}

void right_reverse(uint8_t speed) {
    uint8_t s = constrain(speed, 0, 255);
    analogWrite(PIN_RIGHT_RPWM, s);
    analogWrite(PIN_RIGHT_LPWM, 0);
}

void forward(uint8_t speed) {
    left_forward(speed);
    right_forward(speed);
}

void reverse(uint8_t speed) {
    left_reverse(speed);
    right_reverse(speed);
}

void turn_left(uint8_t speed) {
    left_reverse(speed);
    right_forward(speed);
}

void turn_right(uint8_t speed) {
    left_forward(speed);
    right_reverse(speed);
}

void stop(void) {
    analogWrite(PIN_LEFT_RPWM, 0);
    analogWrite(PIN_LEFT_LPWM, 0);
    analogWrite(PIN_RIGHT_RPWM, 0);
    analogWrite(PIN_RIGHT_LPWM, 0);
}
