# MOD_08 System Integration and Testing

## Purpose
This module focuses on the verification of all submodules, providing end-to-end testing routines to ensure system reliability before final demonstration.

## Author Information
* **Ayşe Feyza SERBEST** - Student ID: [ID]

## Dependencies
* **Internal**: All project modules (MOD-01 through MOD-07).

## Quick-start Integration
```c
#include "system_test.h"

void setup() {
    if (test_run_self_check()) {
        // System healthy
    }
}
```

## API Summary
| Function | Parameters | Return Value | Description |
| :--- | :--- | :--- | :--- |
| `test_run_self_check` | `void` | `int` | Verifies that all sensors and actuators are responsive. |
| `test_simulate_fire_event` | `void` | `void` | Forces a software-simulated fire detection to test navigation. |

## Known Limitations and TODOs
* **Limitation**: Testing environment must be strictly controlled to prevent accidental sensor triggers.
* **TODO**: Develop an automated unit test suite for the FSM logic.

## Version History
* **v0.1 (2026-03-28)**: Initial test routines for hardware check.
