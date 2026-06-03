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

void left_forward(void) {
    analogWrite(PIN_LEFT_RPWM, MOTOR_SPEED);
    analogWrite(PIN_LEFT_LPWM, 0);
}

void left_reverse(void) {
    analogWrite(PIN_LEFT_RPWM, 0);
    analogWrite(PIN_LEFT_LPWM, MOTOR_SPEED);
}

void right_forward(void) {
    analogWrite(PIN_RIGHT_RPWM, 0);
    analogWrite(PIN_RIGHT_LPWM, MOTOR_SPEED);
}

void right_reverse(void) {
    analogWrite(PIN_RIGHT_RPWM, MOTOR_SPEED);
    analogWrite(PIN_RIGHT_LPWM, 0);
}

void forward(void) {
    left_forward();
    right_forward();
}

void reverse(void) {
    left_reverse();
    right_reverse();
}

void turn_left(void) {
    left_reverse();
    right_forward();
}

void turn_right(void) {
    left_forward();
    right_reverse();
}

void stop(void) {
    analogWrite(PIN_LEFT_RPWM, 0);
    analogWrite(PIN_LEFT_LPWM, 0);
    analogWrite(PIN_RIGHT_RPWM, 0);
    analogWrite(PIN_RIGHT_LPWM, 0);
}
