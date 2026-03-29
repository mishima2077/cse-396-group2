# MOD-04 — Motion Control SW

## Purpose
Provides the differential drive system, offering forward/backward/turn logic and speed control to navigate the rover toward target flames.

## Authors
| Name              | Student ID       |
|-------------------|------------------|
| Ahmet Halil YAMLI | 220104004957     |
| Derya UYSAL       | 220104004045     |

## Dependencies
* **Standard C Libraries:** `<stdint.h>`
* **Hardware Drivers:** Locomotion HW (MOD-03) `locomotion_hw.h`
* **External Modules:** None (Primary actuator driver)

## Quick-start Integration
To integrate this module, include the header and initialize the hardware during the setup phase:

```c
#include "motion_control.h"

void setup() {
    // Initialize GPIO and PWM channels
    if (motion_init() == MOTION_OK) {
        // Driver ready
    }
}

void loop() {
    // Drive forward at speed 150 (0-255 range)
    motion_drive(MOTION_DIR_FORWARD, 150);
}
```

## API Summary
| Function | Parameters | Return Value | Description |
| :--- | :--- | :--- | :--- |
| `motion_init` | `void` | `motion_status_t` | Sets up motor driver pins and PWM timers. |
| `motion_drive` | `motion_direction_t dir`, `uint8_t speed` | `motion_status_t` | Executes basic preset maneuvers. |
| `motion_set_differential` | `int16_t left`, `int16_t right` | `motion_status_t` | Individual control of left/right motor speeds. |
| `motion_get_state` | `motion_state_t *out` | `void` | Copies current speed and direction telemetry. |
| `motion_emergency_stop` | `void` | `void` | Forces all motor outputs to zero immediately. |

## Known Limitations and TODOs
* **Limitation:** No acceleration ramping; sudden starts may cause wheel slippage.
* **TODO:** Integrate encoder feedback for closed-loop speed control.
* **TODO:** Add safety timeout if no command is received within 1 second.

## Version History
* **v0.1 (2026-03-28):** Initial draft with basic movement and differential drive support.
