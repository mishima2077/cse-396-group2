# MOD-07 — Autonomy SW

## Purpose
Implements a Finite State Machine (FSM) to control searching, approaching, and extinguishing fire.

## Authors
| Name              | Student ID       |
|-------------------|------------------|
| Ayşe Feyza SERBEST| 220104004052     |
| Görkem UYSAL      | 230104004174     |

## Dependencies

* **MOD-01 (Flame HW)** → raw sensor readings
* **MOD-02 (Flame Detect. SW)** → flame structure (`flame_data_t`) including intensity and direction
* **MOD-04 (Motion Control)** → movement commands using `motion_direction_t`
* **MOD-05 (Distance Sensing)** → obstacle detection
* **MOD-06 (Fire Suppression)** → pump control

---

## Quick-start Integration

```c
#include "autonomy_sw.h"

void setup() {
    autonomy_init();
}

void loop() {
    autonomy_update();
}
```

---

## API Summary

| Function | Parameters | Return Value | Description |
| :--- | :--- | :--- | :--- |
| `autonomy_init` | `void` | `void` | Initializes the FSM and sets the initial state |
| `autonomy_update` | `const autonomy_input_t *in` | `void` | Processes input data and updates FSM state |
| `autonomy_get_output` | `autonomy_output_t *out` | `void` | Returns current motion and actuator commands |
| `autonomy_get_current_state` | `void` | `autonomy_state_t` | Returns the current FSM state |
| `autonomy_reset` | `void` | `void` | Resets FSM to initial state |
| `autonomy_state_to_string` | `autonomy_state_t state` | `const char*` | Converts state enum to readable string for debugging |

---

## Known Limitations and TODOs

### Limitations

* FSM is linear and does not handle complex recovery scenarios
* No handling of lost flame signal
* No filtering for noisy sensor data

### TODOs

* Add `STATE_LOST_TARGET` for flame loss handling
* Implement obstacle-aware navigation
* Add speed control based on distance
* Introduce timeout mechanism for states

---

## Version History

* **v0.1 (2026-03-28)**: Initial FSM structure and state transitions
* **v0.2 (planned)**: Improved state handling and robustness
