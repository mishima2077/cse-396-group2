# MOD_08 — System Integration and Testing

## Purpose

Provides validation, self-check, and end-to-end testing routines to ensure all system modules operate correctly together.

---

## Author Information

* **Ayşe Feyza SERBEST** - Student ID: [220104004052]

---

## Dependencies

* **MOD-01 (Flame HW)** → sensor validation
* **MOD-02 (Flame SW)** → detection verification
* **MOD-03 (Locomotion HW)** → motor testing
* **MOD-04 (Motion Control)** → movement verification
* **MOD-05 (Distance Sensing)** → obstacle detection validation
* **MOD-06 (Fire Suppression)** → pump testing
* **MOD-07 (Autonomy)** → full system behavior testing

---

## Quick-start Integration

```c
#include "system_test.h"

void setup() {
    if (!test_run_self_check()) {
        // Handle failure (halt or debug)
        while (1);
    }
}

void loop() {
    // Optional: run simulation or periodic checks
    test_simulate_fire_event();
}
```

---

## API Summary

| Function | Parameters | Return Value | Description |
| :--- | :--- | :--- | :--- |
| `test_init` | `void` | `void` | Initializes the test module |
| `test_set_mode` | `test_mode_t mode` | `void` | Sets test mode (real or simulation) |
| `test_run_self_check` | `void` | `test_status_t` | Runs full system self-check |
| `test_get_report` | `test_report_t *report` | `void` | Retrieves detailed test results |
| `test_set_simulation_data` | `const test_simulation_input_t *data` | `void` | Sets simulated input data |
| `test_update` | `void` | `void` | Performs periodic monitoring and testing |

---

## Known Limitations and TODOs

### Limitations

* Test routines depend on controlled environment conditions
* Simulation is limited and does not fully replicate real-world behavior
* No detailed error reporting for failed components

### TODOs

* Add detailed test reporting for each module
* Extend simulation scenarios (different distances and directions)
* Implement continuous system monitoring
* Add automated test logging mechanism

---

## Version History

* **v0.1 (2026-03-28)**: Initial self-check and simulation functions
* **v0.2 (planned)**: Enhanced reporting and advanced simulation support
