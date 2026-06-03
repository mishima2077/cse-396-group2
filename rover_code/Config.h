#ifndef CONFIG_H
#define CONFIG_H

#include <Arduino.h>

// ---- Motor Driver Pins (BTS7960 x2) ------------------------------------------------
// Left motor driver
constexpr uint8_t PIN_LEFT_LPWM = 6;   // PWM forward
constexpr uint8_t PIN_LEFT_RPWM = 5;   // PWM reverse
constexpr uint8_t PIN_LEFT_LEN  = 9;   // left enable
constexpr uint8_t PIN_LEFT_REN  = 8;   // right enable

// Right motor driver
constexpr uint8_t PIN_RIGHT_LPWM = 11;  // PWM forward
constexpr uint8_t PIN_RIGHT_RPWM = 10;  // PWM reverse
constexpr uint8_t PIN_RIGHT_LEN  = 13;  // left enable
constexpr uint8_t PIN_RIGHT_REN  = 12;  // right enable

// ---- Ultrasonic Distance Sensors (HC-SR04 x3) ------------------------------------
constexpr uint8_t PIN_TRIG_LEFT   = A5;
constexpr uint8_t PIN_ECHO_LEFT   = A4;
constexpr uint8_t PIN_TRIG_CENTER = 2;
constexpr uint8_t PIN_ECHO_CENTER = 4;
constexpr uint8_t PIN_TRIG_RIGHT  = A1;
constexpr uint8_t PIN_ECHO_RIGHT  = A0;

// ---- Fire Detection Sensors -------------------------------------------------------
constexpr uint8_t PIN_FLAME_AO = A3;  // analog output
constexpr uint8_t PIN_FLAME_DO = A2;  // digital output (LOW = fire detected)

// ---- Water Pump ----------------------------------------------------------------
constexpr uint8_t PIN_WATER_PUMP = 7;  // MOSFET/relay gate

// ---- Serial Communication -------------------------------------------------------
constexpr unsigned long SERIAL_BAUD = 115200UL;

// ---- Sonar Configuration -------------------------------------------------------
constexpr uint16_t SONAR_MAX_CM = 340;
constexpr unsigned long SONAR_TRIG_US = 10UL;

// ---- Motor Speed Levels (PWM 0..255) -------------------------------------------
constexpr uint8_t MOTOR_SPEED = 255;

#endif // CONFIG_H
