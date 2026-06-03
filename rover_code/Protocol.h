#ifndef PROTOCOL_H
#define PROTOCOL_H

#include <stdint.h>

// ---- Arduino → Raspberry Pi (sensor telemetry) ----
// Format: D,<left>,<center>,<right>,<flame_analog>,<flame_digital>\n
// Example: D,150,340,200,512,0\n
// - left, center, right: 0-340 (cm), 0 = no object detected
// - flame_analog: 0-1023 (ADC reading)
// - flame_digital: 0/1 (0=fire detected, 1=no fire)

// ---- Raspberry Pi → Arduino (commands) ----
// Format: <CMD>\n or <CMD>,<param>\n
// Supported commands:
//   FWD or FORWARD\n       (move forward)
//   REV or REVERSE\n       (move backward)
//   TURN_L or LEFT\n       (turn left)
//   TURN_R or RIGHT\n      (turn right)
//   STOP\n                 (stop all motors)
//   PUMP_ON\n              (start water pump)
//   PUMP_OFF\n             (stop water pump)
//
// Speed is hardcoded in Config.h (MOTOR_SPEED)

struct SensorData {
    uint16_t distance_left;
    uint16_t distance_center;
    uint16_t distance_right;
    uint16_t flame_analog;
    uint8_t  flame_digital;
};

#endif // PROTOCOL_H
