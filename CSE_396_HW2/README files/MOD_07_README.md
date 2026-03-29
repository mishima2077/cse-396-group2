# MOD_07 Decision and Autonomy Software

## Purpose
The central logic module that implements the Finite State Machine (FSM) to coordinate searching, approaching, and extinguishing the fire.

## Author Information
* **Ayşe Feyza SERBEST** - Student ID: [ID]

## Dependencies
* **Internal**: MOD-01, MOD-02, MOD-04, MOD-05, MOD-06.

## Quick-start Integration
```c
#include "autonomy_sw.h"

void loop() {
    autonomy_update(); // Run FSM logic
}
```

## API Summary
| Function | Parameters | Return Value | Description |
| :--- | :--- | :--- | :--- |
| `autonomy_update` | `void` | `void` | Evaluates system state and triggers actions in other modules. |
| `autonomy_get_current_state` | `void` | `autonomy_state_t` | Returns the current active state in the FSM. |

## Known Limitations and TODOs
* **Limitation**: The FSM is currently linear; it does not handle recovery from lost flame signals well.
* **TODO**: Add a "Lost Target" state for 360-degree searching.

## Version History
* **v0.1 (2026-03-28)**: Basic state transitions defined.
