#ifndef CONFIG_H
#define CONFIG_H

#include <Arduino.h>

// ---- BTS7960 Motor Sürücü Pinleri --------------------------------------------------
// Sol sürücü
constexpr uint8_t PIN_LEFT_LPWM = 6;   // PWM ileri
constexpr uint8_t PIN_LEFT_RPWM = 5;   // PWM geri
constexpr uint8_t PIN_LEFT_LEN  = 9;   // sol enable
constexpr uint8_t PIN_LEFT_REN  = 8;   // sağ enable
// Sağ sürücü
constexpr uint8_t PIN_RIGHT_LPWM = 11;  // PWM ileri
constexpr uint8_t PIN_RIGHT_RPWM = 10;  // PWM geri
constexpr uint8_t PIN_RIGHT_LEN  = 13;  // sol enable
constexpr uint8_t PIN_RIGHT_REN  = 12;  // sağ enable

// ---- HC-SR04 Ultrasonik Pinleri ----------------------------------------------------
constexpr uint8_t PIN_TRIG_LEFT   = A5;
constexpr uint8_t PIN_ECHO_LEFT   = A4;
constexpr uint8_t PIN_TRIG_CENTER = 2;
constexpr uint8_t PIN_ECHO_CENTER = 4;
constexpr uint8_t PIN_TRIG_RIGHT  = A1;
constexpr uint8_t PIN_ECHO_RIGHT  = A0;

// ---- Yangın Misyonu Donanımı -------------------------------------------------------
constexpr uint8_t PIN_WATER_PUMP = 7;   // R385 tetik (MOSFET/röle gate)
constexpr uint8_t PIN_FLAME_AO   = A3;  // flame sensor analog çıkış
constexpr uint8_t PIN_FLAME_DO   = A2;   // flame sensor dijital çıkış (LOW = ateş var)
// D0/D1 → Pi serial (boş bırak)

// ---- Sonar Sınırı (cm) -------------------------------------------------------------
constexpr uint16_t SONAR_MAX_CM = 340;

// ---- PWM Hızları (0..255) — slave mode komutlarında speed=0 gelirse varsayılan ----
constexpr uint8_t SPEED_CRUISE   = 180;
constexpr uint8_t SPEED_TURN     = 200;
constexpr uint8_t SPEED_REVERSE  = 170;
constexpr uint8_t SPEED_APPROACH = 160;

// ---- Sonar Zamanlama (us / ms) -----------------------------------------------------
constexpr unsigned long SONAR_TIMEOUT_US  = 20000UL;
constexpr unsigned long SONAR_TRIG_US     = 10UL;
constexpr unsigned long SONAR_SETTLE_MS   = 5UL;
constexpr unsigned long SONAR_TRIG_PRE_US = 4UL;

// ---- Serial Protokol ---------------------------------------------------------------
constexpr unsigned long SERIAL_BAUD    = 115200UL;
constexpr uint8_t       SERIAL_BUF_LEN = 32;
// Pi → Arduino: "FORWARD,<s>" | "REVERSE,<s>" | "TURN_LEFT,<s>" | "TURN_RIGHT,<s>"
//               "STOP" | "PUMP_ON" | "PUMP_OFF" | "ROAM"
// Arduino → Pi: "SONAR,<L>,<C>,<R>\n"  |  "FLAME,<raw>\n"

// ---- Sensör Raporlama (ms) ---------------------------------------------------------
constexpr unsigned long SONAR_REPORT_MS = 100UL;   // Arduino → Pi sonar aralığı
constexpr unsigned long FLAME_REPORT_MS = 200UL;   // Arduino → Pi flame aralığı

#endif // CONFIG_H
