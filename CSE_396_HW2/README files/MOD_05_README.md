# MOD_05 Obstacle and Distance Sensing

## Purpose
This module integrates the HC-SR04 ultrasonic sensor to measure distances and provide safety thresholds for the rover's autonomous movement.

## Author Information
* **Ahmet Halil YAMLI** - Student ID: [ID]
* **Derya UYSAL** - Student ID: [ID]
* **Mehmet Alp ATAY** - Student ID: [ID]
* **Adil Mert ERGÖRÜN** - Student ID: [ID]

## Dependencies
* **Hardware**: HC-SR04 Ultrasonic sensor.
* **System**: Microsecond-accurate timing (pulseIn or timer interrupts).

## Quick-start Integration
```c
#include "distance_sensing.h"

void loop() {
    if (distance_is_unsafe()) {
        // Stop the rover
    }
}
```

## API Summary
| Function | Parameters | Return Value | Description |
| :--- | :--- | :--- | :--- |
| `distance_init` | `void` | `int` | Initializes trigger and echo pins for the ultrasonic sensor. |
| `distance_read_cm` | `void` | `uint16_t` | Triggers a ping and returns the calculated distance in cm. |
| `distance_is_unsafe` | `void` | `int` | Returns 1 if an object is closer than the safety threshold. |

## Known Limitations and TODOs
* **Limitation**: Ultrasonic waves can be absorbed by soft surfaces, leading to inaccurate readings.
* **TODO**: Implement a temperature compensation algorithm for speed of sound.

## Version History
* **v0.1 (2026-03-28)**: Basic ping/echo logic and threshold check.
