# Fire-Fighting Rover — Project Context

## Overview

Autonomous fire-detection and suppression rover built on two cooperating compute units:
- **Arduino Mega** — real-time hardware controller (motors, sensors, pump)
- **Raspberry Pi** — computer vision brain (YOLOv8 fire detection, autonomy logic, web dashboard)

The two boards communicate over a single USB serial link at 115200 baud.

---

## Hardware

| Component | Count | Notes |
|-----------|-------|-------|
| Arduino Mega | 1 | Motor + sensor controller |
| Raspberry Pi | 1 | YOLO inference + autonomy |
| BTS7960 motor driver | 2 | One per side (differential drive) |
| HC-SR04 ultrasonic | 3 | Left / Center / Right |
| IR flame sensor | 1 | Analog + digital outputs |
| Water pump | 1 | MOSFET/relay on pin 7 |
| USB camera | 1 | Max sensor resolution, 30 fps |

### Pin Map (Arduino)

```
Left  motor driver : LPWM=6  RPWM=5  LEN=9  REN=8
Right motor driver : LPWM=11 RPWM=10 LEN=13 REN=12
Sonar LEFT         : TRIG=A5  ECHO=A4
Sonar CENTER       : TRIG=2   ECHO=4
Sonar RIGHT        : TRIG=A1  ECHO=A0
Flame sensor       : AO=A3    DO=A2
Water pump         : PIN=7
Serial             : 115200 baud (USB)
```

---

## Repository Layout

```
rover_code/          ← Arduino firmware (C++)
  rover_code.ino     main loop
  Config.h           all pin + baud constants
  Protocol.h         wire format + SensorData struct
  SerialLink.{h,cpp} TX sensor frames / RX commands
  Motors.{h,cpp}     BTS7960 PWM control
  Commands.{h,cpp}   parse CMD,SPEED strings → motor calls
  distance.{h,cpp}   HC-SR04 round-robin (non-blocking)
  flame.{h,cpp}      IR sensor read
  water_pump.{h,cpp} pump on/off

pi_code/             ← Raspberry Pi Python
  dashboard_server.py  Flask-SocketIO server + video + brain
  align_logic.py       autonomous FSM (pure logic, no I/O)
  templates/
    index.html         browser dashboard (MJPEG + WebSocket)
  models/
    best.pt            YOLOv8 fire detection weights
  test/
    command_sender.py  CLI manual command tool
    sensor_monitor.py  CLI sensor readout tool
```

---

## Serial Protocol

### Arduino → Pi (telemetry, every 100 ms)

```
D,<left>,<center>,<right>,<flame_analog>,<flame_digital>\n
```

| Field | Type | Range | Meaning |
|-------|------|-------|---------|
| left / center / right | uint16 | 0–340 cm | 0 = no echo (clear) |
| flame_analog | uint16 | 0–1023 | ADC reading |
| flame_digital | uint8 | 0 or 1 | **0 = fire detected** (active LOW) |

### Pi → Arduino (commands)

```
<CMD>\n          — for STOP, PUMP_ON, PUMP_OFF
<CMD>,<speed>\n  — for FWD, REV, TURN_L, TURN_R  (speed 0-255)
```

Supported commands: `FWD`, `REV`, `TURN_L`, `TURN_R`, `STOP`, `PUMP_ON`, `PUMP_OFF`

---

## Arduino Firmware (`rover_code/`)

### Main Loop (non-blocking)

```
setup() → init all modules
loop()  → distance_update()      — round-robin sonar (one sensor / 20 ms)
         flame_update()           — read ADC + digital pin
         collect sensor_data
         every 100 ms → link.sendSensors()
         link.receiveCommand()    — parse incoming line → command_execute()
```

### Motor Driver (BTS7960)

`turn_left`  = left motor reverse + right motor forward (pivot turn)
`turn_right` = left motor forward + right motor reverse (pivot turn)
`forward` / `reverse` = both motors same direction

Speed is always 0–255 PWM, passed directly from the `CMD,SPEED` field received from Pi.

### Distance Sensing

Round-robin scheduler fires one sonar every 20 ms (60 ms full cycle). `pulseIn` timeout = 24 000 µs ≈ 340 cm max range. Zero reading means no echo → treated as "clear" in the Pi brain.

---

## Raspberry Pi Software (`pi_code/`)

### `dashboard_server.py` — Body / Server

Owns all I/O:
- Opens camera (requests max resolution; driver clamps to sensor max)
- Auto-detects Arduino serial port: tries `/dev/ttyUSB0`, `/dev/ttyACM0`, `/dev/ttyUSB1`, `/dev/ttyACM1`
- Runs three background threads: serial reader, video+YOLO, Flask-SocketIO
- Forwards every command from `align_logic` and the browser to Arduino via `send_command()`

Key constants:

| Constant | Value | Purpose |
|----------|-------|---------|
| `YOLO_CONF` | 0.60 | Minimum detection confidence |
| `YOLO_IMGSZ` | 256 | Inference image size (Pi-safe) |
| `YOLO_EVERY_N` | 5 | Run YOLO every 5th frame |
| `MJPEG_QUALITY` | 55 | JPEG encode quality |
| `SENSOR_EMIT_HZ` | 10 | Max WebSocket sensor pushes/sec |
| `FIRE_LABELS` | `{"fire"}` | Only this label triggers alignment |

YOLO result is cached between inference frames — bounding boxes are drawn on every frame even without re-running inference.

### `align_logic.py` — Brain / FSM

Pure decision logic with zero I/O. Called once per video frame via `aligner.update(main_target, frame_w, sensors, now)`. Returns a command string or `None`.

#### Speed Tiers

| Constant | Value | Used for |
|----------|-------|---------|
| `SPEED_ALIGN` | 50 | Centering turns (slow, precise) |
| `SPEED_APPROACH` | 200 | Forward toward fire |
| `SPEED_SCAN` | 50 | 360° search spin |
| `SPEED_IDLE` | 200 | Free-roam forward + avoidance turns |

#### Hardcoded Turn Durations

These need rig measurement and update:

| Constant | Estimated | Meaning |
|----------|-----------|---------|
| `TURN_90_ALIGN_MS` | 6120 | 90° pivot at speed 50 |
| `TURN_90_IDLE_MS` | 1530 | 90° pivot at speed 200 |
| `TURN_180_IDLE_MS` | 3060 | 180° pivot at speed 200 |
| `SCAN_360_MS` | 24480 | Full 360° spin at speed 50 |

#### Alignment / Approach Tuning

| Constant | Value | Meaning |
|----------|-------|---------|
| `ALIGNMENT_THRESHOLD` | 40 px | Dead-zone — within this = "centered" |
| `REALIGN_THRESHOLD` | 80 px | Max drift during approach before re-center |
| `CAMERA_FOV` | 55° | Horizontal field of view |
| `SETTLE_TIME` | 0.35 s | Wait after turn before re-deciding |
| `MIN_TURN_MS` | 60 ms | Minimum motor-on time for any turn |
| `FIRE_LOST_GRACE` | 1.0 s | Fire must be absent this long before search starts |
| `STOP_DISTANCE_CM` | 20 cm | Front sensor threshold to stop at fire |
| `APPROACH_TIMEOUT` | 8.0 s | Safety: abort approach if not arrived |

#### Free-Roam Tuning

| Constant | Value | Meaning |
|----------|-------|---------|
| `OBSTACLE_CM` | 30 cm | Front reading that counts as blocking |
| `SIDE_CM` | 30 cm | Side reading above which = "free to turn" |
| `ROAM_SCAN_INTERVAL` | 10.0 s | Seconds of clear driving before re-scan |

#### State Machine

```
         ┌─────────────────────────────────────────────────────────┐
         │  FIRE PREEMPTION (checked every frame, highest priority) │
         │  Fire seen while SCANNING or ROAMING → abort → IDLE     │
         └─────────────────────────────────────────────────────────┘

IDLE ──────── no fire > 1s ────────────────────────→ SCANNING
  │                                                      │ 360° done, no fire
  │  fire off-center                                     ↓
  └─────────────────────→ TURNING                    ROAMING ←──────────────────┐
                              │ turn done                │ 10s clear             │
                              ↓                          │                       │
                          SETTLING                   360° re-scan            obstacle?
                              │ settled                  ↓                       │
                              ↓                       SCANNING               ROAMING (turn phase)
  fire centered ──────────→ IDLE                                                 │ turn done
  fire centered + close ──→ ARRIVED                                              └───────────────
  |                                                  
  └─ start approach ──────→ APPROACH
                              │ arrived / drifted / timeout / fire lost
                              ↓
                           IDLE / ARRIVED
```

**Fire preemption rule:** when `main_target` is not None and state is SCANNING or ROAMING → state forced back to IDLE immediately. No grace delay applies — fire detection is instant.

**Grace timer rule:** when `main_target` is None, `fire_lost_since` starts. If fire reappears within `FIRE_LOST_GRACE=1.0s`, timer resets. Only after 1 s of confirmed absence does the FSM start a scan. Prevents flicker from frame-skip triggering needless searches.

**Avoidance turn resets 10s scan timer** — clock restarts when the avoidance turn completes and forward driving resumes.

**Fire extinguished after arrival** — fire_lost_since starts, grace period elapses, scan begins fresh.

---

## Browser Dashboard (`pi_code/templates/index.html`)

Single-page app, no build step. Opens via `http://<pi-ip>:5000`.

- **MJPEG stream** — `/video_feed` endpoint, YOLOv8 bounding boxes drawn server-side
- **WebSocket events** received:
  - `sensor` — left/center/right distances + flame ADC + flame digital
  - `fire_yolo` — detected bool, count, cx, cy, deviation px, confidence
  - `log` — timestamped log lines with CSS class (`info` / `warn` / `fire` / `cmd`)
- **WebSocket events** sent:
  - `command` — `{cmd, speed}` for motion, `{cmd}` for STOP/pump
- **Keyboard shortcuts** — Arrow keys = FWD/REV/LEFT/RIGHT, Space = STOP
- **Speed slider** — 0–255, applied to all manual motion commands

---

## Development Tools

### `pi_code/test/command_sender.py`

Interactive CLI for manual rover control. Accepts shorthand (`f`, `l`, `r`, `s`) and full command names with optional speed (`fwd 150`). Auto-detects serial port; override with first argv.

### `pi_code/test/sensor_monitor.py`

Read-only sensor readout. Parses `D,...` lines from Arduino and prints formatted table. Useful for verifying sonar and flame sensor readings before running autonomy.

---

## Deployment

```bash
# Copy to Pi
scp pi_code/align_logic.py pi_code/dashboard_server.py \
    mertergorun@172.20.10.2:~/fire_dashboard/

# Install Python dependencies on Pi
pip install ultralytics opencv-python flask flask-socketio pyserial huggingface_hub

# Run
python3 ~/fire_dashboard/dashboard_server.py

# Run without YOLO (sensor + manual control only)
python3 ~/fire_dashboard/dashboard_server.py --no-yolo

# Run without autonomous alignment (observe only)
python3 ~/fire_dashboard/dashboard_server.py --no-align

# Force specific serial port
python3 ~/fire_dashboard/dashboard_server.py --serial /dev/ttyUSB0
```

---

## YOLO Model

- Architecture: YOLOv8
- Source: `SalahALHaismawi/yolov26-fire-detection` (HuggingFace)
- Local path: `pi_code/models/best.pt`
- Inference size: 256×256 (Pi-safe; 320+ causes OOM/crash on Pi)
- Tracked labels: `fire` only — all other classes ignored
- Frame skip: runs every 5th frame, cached result drawn on all frames
