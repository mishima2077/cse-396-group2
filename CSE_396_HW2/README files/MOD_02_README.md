# FLAME_DETECTION — Flame Detection Module

Reads three IR flame sensors mounted on the rover's front face and exposes the detected flame direction and intensity to the Control & Decision module.

---

## Authors

| Name              | Student ID       |
|-------------------|------------------|
| Mehmet Alp ATAY   | 220104004020     |
| Adil Mert ERGÖRÜN | 220104004048     |

---

## Dependencies

| Dependency | Type | Notes |
|-----------|------|-------|
| `<stdint.h>` | System | Standard integer types |
| Arduino core / ESP32 Arduino | External SDK | `analogRead()`, `millis()` |
| `fire_suppression.h` | None (consumer only) | Suppression module consumes this module's output via MOD-4 |

---

## Quick-Start Integration Example

```c
#include "flame_detection.h"

void setup() {
    Serial.begin(115200);

    if (flame_init() != FLAME_OK) {
        Serial.println("Flame sensor init failed!");
        while (1);
    }

    /* Start periodic sampling with an optional callback */
    flame_start(NULL);
}

void loop() {
    flame_data_t data;

    if (flame_read(&data) == FLAME_OK && data.detected) {
        switch (data.direction) {
            case FLAME_DIR_LEFT:   Serial.println("Flame LEFT");   break;
            case FLAME_DIR_CENTER: Serial.println("Flame AHEAD");  break;
            case FLAME_DIR_RIGHT:  Serial.println("Flame RIGHT");  break;
            default: break;
        }
    }

    delay(FLAME_SAMPLE_INTERVAL_MS);
}
```

---

## API Summary

| Function | Parameters | Return | Description |
|----------|-----------|--------|-------------|
| `flame_init()` | `void` | `flame_status_t` | Initialises GPIO pins and sensor hardware |
| `flame_start(cb)` | `flame_cb_t cb` | `flame_status_t` | Starts periodic sampling; callback optional |
| `flame_read(out)` | `flame_data_t *out` | `flame_status_t` | Reads latest sample into caller-owned struct |
| `flame_get_direction()` | `void` | `flame_direction_t` | Returns dominant flame direction without full read |
| `flame_stop()` | `void` | `void` | Stops sampling and powers down sensors |

### Data Types

| Type | Kind | Description |
|------|------|-------------|
| `flame_status_t` | `enum` | `FLAME_OK`, `FLAME_ERR_INIT`, `FLAME_ERR_NO_SENSOR`, `FLAME_ERR_TIMEOUT` |
| `flame_direction_t` | `enum` | `FLAME_DIR_NONE`, `FLAME_DIR_LEFT`, `FLAME_DIR_CENTER`, `FLAME_DIR_RIGHT` |
| `flame_data_t` | `struct` | Raw ADC values, The highest ADC reading, detected flag, direction, timestamp |
| `flame_cb_t` | `typedef` | `void (*)(const flame_data_t *)` — callback on each sample |

### Constants / Macros

| Macro | Value | Description |
|-------|-------|-------------|
| `FLAME_SENSOR_COUNT` | `3` | Number of IR sensors |
| `FLAME_THRESHOLD` | `500` | ADC threshold for flame detection |
| `FLAME_SAMPLE_INTERVAL_MS` | `50` | Sampling period in ms (20 Hz) |
| `FLAME_ADC_MAX` | `1023` | Maximum 10-bit ADC reading |

---

## Known Limitations & TODOs

- [ ] **Ambient light interference**: Strong sunlight or incandescent lamps may cause false positives. A shielded sensor housing is recommended for testing.
- [ ] **Single-axis detection only**: The current design detects left/center/right but not elevation angle of the flame.
- [ ] **Callback thread safety**: `flame_cb_t` is called from the sampling loop context; consumers must not block inside the callback.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| v0.1 | 2026-03-28 | Initial draft — `flame_init`, `flame_read`, `flame_get_direction`, `flame_stop`, core data types |
