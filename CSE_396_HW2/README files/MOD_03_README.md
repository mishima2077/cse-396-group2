# MOD_03 Locomotion Hardware

## Purpose
This module manages the physical chassis assembly, motor driver wiring, and battery integration to provide low-level control of the rover's wheels.

## Author Information
* **Cemal GÜMÜŞ** - Student ID: [ID]
* **Melih KAZANCI** - Student ID: 230104004909

## Dependencies
* **Hardware**: L298N Motor Driver, DC Motors, and LiPo Battery.
* **Software**: Standard Arduino/ESP32 GPIO and PWM peripheral libraries.

## Quick-start Integration
Include the header and initialize the hardware to control the motors directly.

```c
#include "locomotion_hw.h"

void setup() {
    // Initialize motor driver pins
    if (loco_hw_init() == LOCO_HW_OK) {
        // Hardware is ready
    }
}

void loop() {
    // Set left motor to move forward at 50% power
    loco_hw_set_motor(LOCO_HW_LEFT, 128, true);
}
```

## API Summary
| Function | Parameters | Return Value | Description |
| :--- | :--- | :--- | :--- |
| `loco_hw_init` | `void` | `loco_hw_status_t` | Configures GPIO pins and PWM timers for the motor driver. |
| `loco_hw_set_motor` | `loco_hw_side_t side`, `uint8_t pwm`, `bool fwd` | `loco_hw_status_t` | Sets the raw PWM duty cycle and rotation direction for one side. |
| `loco_hw_disable_motors`| `void` | `void` | Immediately cuts PWM output to both motors (coasting). |
| `loco_hw_brake` | `void` | `void` | Engages active electrical braking on the motor driver. |
| `loco_hw_is_power_stable`| `void` | `bool` | Validates that battery voltage is within safe operational levels. |

## Known Limitations and TODOs
* **Limitation**: Does not include high-level kinematics; those are handled by MOD-04.
* **TODO**: Implement real-time battery voltage monitoring via an ADC pin.
* **TODO**: Perform mechanical stability checks at high speeds.

## Version History
* **v0.1 (2026-03-28)**: Initial draft; defined pin-level control functions for L298N integration.
