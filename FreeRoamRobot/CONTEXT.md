# FreeRoamRobot — Project Context

## Overview

Autonomous fire-fighting robot. Raspberry Pi handles all perception and decision-making. Arduino Uno executes motor and pump commands. Robot roams freely, detects fire via YOLO camera, navigates toward it, and extinguishes with water pump.

---

## Hardware

| Component | Part | Notes |
|-----------|------|-------|
| Brain (high-level) | Raspberry Pi | Runs Python, YOLO, FSM |
| Brain (low-level) | Arduino Uno | Executes commands, reports sensors |
| Drive | 4WD chassis + 2x L298N | Skid-steer / tank kinematics |
| Distance sensors | 3x HC-SR04 | Left, Center, Right |
| Water pump | R385 | MOSFET/relay on D3 |
| Flame sensor | Analog (AO) | Forward-facing, mounted co-planar with nozzle |
| Camera | USB/CSI cam | YOLO input, faces forward |

### Arduino Pin Map

```
D2/D4/D5(PWM) → Left motor (L298N IN1, IN2, ENA)
D6(PWM)/D7/D8 → Right motor (L298N ENB, IN3, IN4)
D9/D10        → Sonar LEFT  (TRIG/ECHO)
D11/D12       → Sonar CENTER (TRIG/ECHO)
A0/A1         → Sonar RIGHT  (TRIG/ECHO)
D3(PWM)       → Water pump gate
A2            → Flame sensor AO
D0/D1         → Serial (Pi UART — leave free)
```

---

## Software Architecture

```
Raspberry Pi
├── main.py                 — entry point, thread orchestration
├── pi/
│   ├── config.py           — all Pi-side constants
│   ├── model_utils.py      — YOLO model download/cache
│   ├── serial_bridge.py    — send() / read_arduino()
│   ├── yolo_tracker.py     — YOLO thread (centroid tracker)
│   ├── arduino_controller.py — Arduino thread (10 Hz FSM loop)
│   └── fsm.py              — free_roam() + fire_mission() FSMs
└── tests/
    └── test_serial_bridge.py

Arduino Uno
├── FreeRoamRobot.ino       — setup() / loop()
├── Config.h                — all Arduino constants
├── SerialLink.h/.cpp       — Pi↔Arduino serial protocol
├── SlaveController.h/.cpp      — command executor + slave timeout
├── SkidSteerMotors.h/.cpp  — motor driver abstraction
├── TripleSonarArray.h/.cpp — non-blocking round-robin sonar
├── WaterPump.h             — pump on/off
└── FlameSensor.h           — raw analog read
```

### Threading Model

```
Main thread   — cv2.imshow GUI (macOS requires main thread)
  └── frame_q (Queue maxsize=2)
YOLO thread   — camera read → YOLO inference → centroid tracking
  └── shared_tracks (dict, protected by tracks_lock)
Arduino thread — 10 Hz: read sensors → FSM → send commands
  └── reads shared_tracks (short lock snapshot)
```

---

## Communication Protocol

### Pi → Arduino (text, newline-terminated)

| Command | Meaning |
|---------|---------|
| `FORWARD,<speed>` | Drive forward at PWM speed (0–255) |
| `REVERSE,<speed>` | Drive reverse |
| `TURN_LEFT,<speed>` | Point-turn left |
| `TURN_RIGHT,<speed>` | Point-turn right |
| `STOP` | Immediate stop |
| `PUMP_ON` | Start water pump |
| `PUMP_OFF` | Stop water pump |
| `ROAM` | (reserved) |

### Arduino → Pi (text, newline-terminated)

| Message | Meaning |
|---------|---------|
| `SONAR,<L>,<C>,<R>` | Distances in cm, every 100ms |
| `FLAME,<raw>` | analogRead 0–1023, every 200ms |

### Slave Timeout Safety

Arduino stops all motors and pump if no Pi command received for `SLAVE_TIMEOUT_MS` (1000ms). Protects against Pi crash or serial disconnect.

---

## Domain Glossary

### Fire Detection
Visual confirmation by YOLO that fire has been **continuously present** in frame for `alert_hold` seconds (default 2.0s). Sets `alerted=True` on a centroid track.

**Design decision:** YOLO is the sole mission trigger. Flame sensor alone cannot start a mission — it lacks spatial (cx) data needed for AIMING state. Flame sensor is exit-only.

### Flame Sensor Reading
Raw analog value (0–1023) from forward-facing flame sensor. Lower = more heat. Used exclusively as SPRAYING exit: fire considered out when reading stays ≥ `FLAME_THRESHOLD_PI` (300) for `FLAME_CLEAR_S` (3.0s) continuously.

### Fire Mission
Autonomous sequence triggered by Fire Detection:
```
AIMING → APPROACHING → SPRAYING → back_to_roam
```
Terminated when Flame Sensor Reading confirms fire is out.

### Free Roam
Default mode. Robot drives forward, avoids obstacles via sonar, performs periodic Survey Scans.

### Survey Scan (370°)
After `OBSERVE_WINDOW_S` (15s) of uninterrupted straight driving, robot spins right slightly more than 360°. Intentional overshoot breaks rotational symmetry — prevents robot from always resuming at the same heading. Overshoot target: 350°–370° (randomizable). Currently fixed at `TURN_370_S` = 2.6s. Needs calibration per chassis.

### Pi Master / Arduino Slave
All decision-making on Raspberry Pi. Arduino only: (1) reports sensors, (2) executes motor/pump commands. No autonomous navigation logic on Arduino.

### Centroid Track
YOLO detection matched frame-to-frame by nearest centroid within `max_dist` (90px). Stores: label, cx/cy, start_ts, last_seen_ts, alerted flag. Track deleted after `max_age` (1.0s) without detection.

### alerted
Boolean on a centroid track. True when fire has been continuously visible for `alert_hold` seconds. Only alerted tracks trigger Fire Mission.

---

## FSM States

### Free Roam States

| State | Action | Exit condition |
|-------|--------|----------------|
| `DRIVE_STRAIGHT` | FORWARD @ SPEED_CRUISE | C < WARNING_ZONE_CM → turn state; elapsed ≥ OBSERVE_WINDOW_S → TURN_370 |
| `TURN_370` | TURN_RIGHT @ SPEED_TURN | elapsed ≥ TURN_370_S → DRIVE_STRAIGHT |
| `TURN_RIGHT_90` | TURN_RIGHT @ SPEED_TURN | elapsed ≥ TURN_90_S → DRIVE_STRAIGHT |
| `TURN_LEFT_90` | TURN_LEFT @ SPEED_TURN | elapsed ≥ TURN_90_S → DRIVE_STRAIGHT |
| `TURN_180_BACK` | REVERSE then TURN_LEFT | elapsed ≥ REVERSE_S + TURN_180_S → DRIVE_STRAIGHT |

**Obstacle priority:** C blocked → if R clear: turn right; elif L clear: turn left; else: TURN_180_BACK.

### Fire Mission States

| State | Action | Exit condition |
|-------|--------|----------------|
| `AIMING` | TURN_LEFT/RIGHT @ SPEED_APPROACH | \|err\| ≤ AIM_DEADBAND_PX → APPROACHING; fire_cx=None → back_to_roam |
| `APPROACHING` | FORWARD @ SPEED_APPROACH | sonar_C ≤ FIRE_STOP_CM → SPRAYING; fire_cx drifts > deadband → back to AIMING; fire_cx=None → back_to_roam |
| `SPRAYING` | PUMP_ON (stationary) | flame ≥ FLAME_THRESHOLD_PI for FLAME_CLEAR_S → PUMP_OFF + back_to_roam |

---

## Calibration Parameters

| Parameter | Location | Current | Notes |
|-----------|----------|---------|-------|
| `WARNING_ZONE_CM` | pi/config.py | 35cm | Free roam obstacle threshold |
| `FIRE_STOP_CM` | pi/config.py | 30cm | Approach stop distance |
| `AIM_DEADBAND_PX` | pi/config.py | 40px | ±6.25% of 640px frame |
| `FLAME_THRESHOLD_PI` | pi/config.py | 300 | Analog: below = fire present |
| `FLAME_CLEAR_S` | pi/config.py | 3.0s | Sustained clear before mission ends |
| `TURN_370_S` | pi/config.py | 2.6s | Survey scan duration — calibrate per chassis |
| `TURN_90_S` | pi/config.py | 0.6s | 90° turn — calibrate per chassis |
| `TURN_180_S` | pi/config.py | 1.2s | 180° turn portion — calibrate per chassis |
| `REVERSE_S` | pi/config.py | 0.7s | Reverse portion of TURN_180_BACK |
| `SPEED_APPROACH` | pi/config.py | 160 PWM | Must be low enough that 100ms pulse < AIM_DEADBAND_PX |
| `SLAVE_TIMEOUT_MS` | — | removed | Timeout deferred; Arduino holds last command |
| `SONAR_REPORT_MS` | Config.h | 100ms | Arduino → Pi sonar rate |
| `FLAME_REPORT_MS` | Config.h | 200ms | Arduino → Pi flame rate |
| `alert_hold` | fire_smoke_alert.py | 2.0s | YOLO continuous detection before alert |
| `MIN_ALERT_CONF` | pi/config.py | 0.60 | Minimum YOLO confidence |

---

## Design Decisions

### YOLO sole mission trigger
Flame sensor alone cannot trigger Fire Mission. Rationale: flame sensor lacks spatial data (camera cx) required for AIMING. Starting a mission with fire_cx=None → immediate back_to_roam.

### Multi-fire handling
If second fire detected while already in Fire Mission, it is silently ignored. Robot finishes current mission, returns to free roam, re-detects. Rationale: simultaneous fires are an edge case; switching mid-mission adds state complexity.

### No side-sonar check during APPROACHING
APPROACHING only checks sonar_C. Rationale: pump spray radius tolerates minor lateral misalignment at 30cm range. Side-obstacle abort would require new state and threshold.

### Post-SPRAYING recovery
After fire extinguished, robot enters DRIVE_STRAIGHT immediately (no reverse). Rationale: WARNING_ZONE_CM (35cm) > FIRE_STOP_CM (30cm), so free_roam detects any solid obstacle and turns away.

### AIMING control: bang-bang
AIMING uses full SPEED_APPROACH regardless of error magnitude. No proportional control. Risk: oscillation if SPEED_APPROACH too high. Mitigation: calibrate SPEED_APPROACH low enough that 100ms pulse stays within AIM_DEADBAND_PX.

### Arduino slave timeout
Removed. Arduino holds last PWM state until new command arrives. Pi does not need to send commands continuously — only on state change (via send_once). Timeout safety deferred.

---

## Known Limitations / Open Issues

- **AIMING oscillation**: bang-bang control may oscillate if SPEED_APPROACH not calibrated correctly. Consider two-speed control if observed on hardware.
- **Survey scan randomization**: TURN_370_S is fixed. Randomizing ±10° (TURN_370_S ± ~0.07s) would further break symmetry.
- **TURN_180 stuck loop**: if robot is wedged in a symmetric dead end, consecutive TURN_180 states are possible. No escape heuristic implemented.
- **sonar_C spike in APPROACHING**: single bad reading ≤ FIRE_STOP_CM triggers SPRAYING prematurely. Consider 2-reading debounce if observed.
- **All timing constants need calibration** on actual hardware (turn durations depend on surface friction, battery voltage, motor characteristics).
