# FIRE_SUPPRESSION — Suppression Hardware Module (MOD-06)

Controls the relay-driven water pump and nozzle that extinguishes detected flames when the rover reaches the safe suppression distance.

---

## Authors

| Name              | Student ID       |
|-------------------|------------------|
| Mehmet Alp ATAY   | 220104004020     |
| Adil Mert ERGÖRÜN | 220104004048     |

---

## Dependencies

* **Hardware**: DC water pump and external relay module
* **MOD-07 (Autonomy SW)** → issues `suppression_cmd_t` commands to this control module
* **Arduino core / ESP32** → standard types, `digitalWrite()`, and `millis()`

---

## Quick-Start Integration Example

```c
#include "fire_suppression.h"

void setup() {
    Serial.begin(115200);

    if (suppression_init() != SUPPRESSION_OK) {
        Serial.println("Suppression module init failed!");
        while (1);
    }
}

void loop() {
    /* Example: activate pump for default duration when triggered by MOD-4 */
    suppression_status_t result = suppression_activate(0); /* 0 = use default duration */

    if (result == SUPPRESSION_OK) {
        Serial.println("Pump activated.");
    } else if (result == SUPPRESSION_ERR_COOLDOWN) {
        Serial.println("Cooldown active, skipping.");
    }

    /* Query state */
    suppression_state_t state;
    suppression_get_state(&state);
    Serial.print("Total activations: ");
    Serial.println(state.total_activations);

    delay(1000);
}
```

### Using `suppression_cmd_t` (from MOD-4 Control Module)

```c
#include "fire_suppression.h"

void handle_control_command(uint8_t should_spray) {
    suppression_cmd_t cmd;
    cmd.activate     = should_spray;
    cmd.duration_ms  = 2000;          /* 2-second burst */
    cmd.issued_at_ms = millis();

    suppression_apply_cmd(&cmd);
}
```

---

## API Summary

| Function | Parameters | Return | Description |
|----------|-----------|--------|-------------|
| `suppression_init()` | `void` | `suppression_status_t` | Initialises relay GPIO pin and pump hardware |
| `suppression_activate(duration_ms)` | `uint16_t duration_ms` | `suppression_status_t` | Activates pump; 0 uses default duration |
| `suppression_deactivate()` | `void` | `suppression_status_t` | Immediately cuts power to the pump |
| `suppression_is_active()` | `void` | `uint8_t` | Returns 1 if pump is currently running |
| `suppression_get_state(out)` | `suppression_state_t *out` | `suppression_status_t` | Fills state struct with current module snapshot |
| `suppression_apply_cmd(cmd)` | `const suppression_cmd_t *cmd` | `suppression_status_t` | Applies a command from Control & Decision (MOD-4) |
| `suppression_stop()` | `void` | `void` | Powers down relay and releases hardware resources |

### Data Types

| Type | Kind | Description |
|------|------|-------------|
| `suppression_status_t` | `enum` | `SUPPRESSION_OK`, `SUPPRESSION_ERR_INIT`, `SUPPRESSION_ERR_COOLDOWN`, `SUPPRESSION_ERR_HARDWARE` |
| `suppression_state_t` | `struct` | `is_active`, `last_activated_ms`, `total_activations` |
| `suppression_cmd_t` | `struct` | `activate`, `duration_ms`, `issued_at_ms` — issued by MOD-4 |

### Constants / Macros

| Macro | Value | Description |
|-------|-------|-------------|
| `SUPPRESSION_PUMP_DURATION_MS` | `3000` | Default pump burst length (ms) |
| `SUPPRESSION_COOLDOWN_MS` | `500` | Minimum time between consecutive activations (ms) |
| `SUPPRESSION_RELAY_PIN` | `7` | GPIO pin driving the relay IN signal |

---

## Known Limitations & TODOs

- [ ] **Water tank level**: There is no sensor to detect when the water reservoir is empty. A float sensor should be added in a future hardware revision.
- [ ] **Relay welding risk**: Rapid repeated activation may cause relay contact welding. The `SUPPRESSION_COOLDOWN_MS` guard mitigates this but should be validated experimentally.
- [ ] **No fire-extinguished verification**: The suppression module does not confirm whether the flame was successfully put out — this must be done by MOD-1 (Flame Detection) via MOD-4.
- [ ] Confirm `SUPPRESSION_RELAY_PIN` GPIO number with the Navigation & Motion team to avoid pin conflicts.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| v0.1 | 2026-03-28 | Initial draft — `suppression_init`, `suppression_activate`, `suppression_deactivate`, `suppression_is_active`, `suppression_get_state`, `suppression_apply_cmd`, `suppression_stop`, core data types |
