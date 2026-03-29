# MOD_01 Flame Sensing Hardware

## Purpose
This module involves the selection, mounting, and wiring of flame sensors to reduce ambient light noise and provide clean signal inputs for detection software.

## Author Information
* **Görkem UYSAL** - Student ID: [ID]

## Dependencies
* **Hardware**: Infrared flame sensor modules, Analog-to-Digital Converter (ADC) pins on the MCU.
* **Software**: None (Low-level hardware driver).

## Quick-start Integration
```c
#include "flame_hw.h"

void setup() {
    flame_hw_init(); // Configure ADC pins
}

void loop() {
    uint16_t sensor_values[3];
    flame_hw_read_raw(sensor_values); // Read current intensity
}
```

## API Summary
| Function | Parameters | Return Value | Description |
| :--- | :--- | :--- | :--- |
| `flame_hw_init` | `void` | `flame_hw_status_t` | Initializes GPIO/ADC pins for sensor communication. |
| `flame_hw_read_raw` | `uint16_t *buffer` | `void` | Populates a buffer with the latest raw ADC readings. |

## Known Limitations and TODOs
* **Limitation**: Analog readings are highly sensitive to ambient sunlight.
* **TODO**: Implement shielding for sensors to narrow the field of view.

## Version History
* **v0.1 (2026-03-28)**: Initial draft for sensor wiring and basic ADC reading.
