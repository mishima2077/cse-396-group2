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
  run.py               launcher → rover.app.main()
  rover/               application package (one responsibility per module)
    config.py          all tunable constants (the one place to fine-tune)
    protocol.py        Arduino wire format: command builders + sensor parsing
    state.py           thread-safe SharedState (sensors / frame / fire)
    serial_link.py     Arduino serial I/O (connect, send, read loop)
    camera.py          camera discovery + capture wrapper
    vision.py          YOLO FireDetector + frame annotation
    autonomy.py        the align/approach/extinguish/roam FSM (pure logic, no I/O)
    controller.py      manual/auto mode policy — decides who drives
    web.py             Flask + SocketIO routes/handlers + MJPEG
    app.py             orchestration / entry point
  templates/
    index.html         dashboard HTML shell (loads /static assets)
  static/
    css/dashboard.css  all dashboard styling
    js/ui.js           socket wiring + live display (distances/YOLO/flame/log)
    js/controls.js     manual/auto toggle + command dispatch + keyboard
    js/map.js          run-report overlay: travel map canvas + timeline + export
    js/recorder.js     run recorder: dead-reckoning + semantic event detection
  models/
    best.pt            YOLOv8 fire detection weights
  test/
    command_sender.py  CLI manual command tool
    sensor_monitor.py  CLI sensor readout tool
    extinguish_test.py forces the FSM into EXTINGUISHING, drives the real Arduino
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

> **Module map.** The Pi software is split into a `rover/` package, one
> responsibility per file (see Repository Layout). `app.py` wires them together;
> `config.py` holds every tunable; `protocol.py` is the single source of truth
> for the Arduino wire format. The descriptions below cover the two most
> involved pieces — the server orchestration and the FSM.

### `rover/app.py` + `rover/web.py` — Body / Server

Owns all I/O:
- Opens camera (requests max resolution; driver clamps to sensor max)
- Auto-detects Arduino serial port: tries `/dev/ttyUSB0`, `/dev/ttyACM0`, `/dev/ttyUSB1`, `/dev/ttyACM1`
- Runs two background threads (serial reader, video+YOLO) plus the Flask-SocketIO server
- Routes commands through `RoverController`: in AUTO the FSM drives; in MANUAL the
  browser drives. `controller.send()` is the choke-point that writes to the
  Arduino (`serial_link.send`) and mirrors every command to the dashboard log.

Key constants (all in `rover/config.py` → `VisionCfg` / `ServerCfg`):

| Constant | Value | Purpose |
|----------|-------|---------|
| `vision.conf` | 0.60 | Minimum detection confidence |
| `vision.imgsz` | 256 | Inference image size (Pi-safe) |
| `vision.every_n` | 5 | Run YOLO every 5th frame |
| `vision.mjpeg_quality` | 55 | JPEG encode quality |
| `server.sensor_emit_hz` | 10 | Max WebSocket sensor pushes/sec |
| `vision.labels` | `{"fire"}` | Only this label triggers alignment |

### `rover/controller.py` — Mode policy

`RoverController` owns the serial link, the `Aligner` FSM, and the manual/auto
flag. It is the only place that decides who drives:
- **AUTO** — `on_frame()` runs the FSM each video frame and sends its command;
  dashboard motion commands are ignored.
- **MANUAL** — the FSM is paused; only `manual_command()` (from the browser)
  moves the rover.
- `set_mode()` always sends `STOP` **and `PUMP_OFF`** on a switch (never leave
  the pump running across a mode change), and resets the FSM when returning to
  AUTO so it re-plans from a clean state.
- The rover **boots in MANUAL** — the operator drives until AUTO is chosen.

YOLO result is cached between inference frames — bounding boxes are drawn on every frame even without re-running inference.

### `rover/autonomy.py` — Brain / FSM

Pure decision logic with zero I/O. Called once per video frame via `aligner.update(deviation, frame_w, sensors, now)` (where `deviation` is the fire's signed px offset from center, or `None` if no fire). Returns a command string or `None`.

#### Mission flow

1. **No fire** → hold still (`STOP`).
2. **Fire off-center** → rotate to center it (`TURN_L/R` @ align speed).
3. **Fire centered, far** → drive forward (`FWD`, **two-tier**: fast far out, slow once inside `APPROACH_SLOW_CM`).
4. **Front ≤ `PUMP_START_CM` (20 cm)** → `STOP`, then `PUMP_ON`, hand off to **DOCKING**.
5. **DOCKING** → closed-loop `FWD`/`REV` nudges until front is `DOCK_TARGET_CM ± DOCK_TOL_CM` (10±2 cm), confirmed over `DOCK_CONFIRM_N` reads → **EXTINGUISHING**.
6. **EXTINGUISHING** → fixed, run-to-completion choreography.
7. **Extinguish done** → reverse ≈10 cm back-off → 360° re-scan → **PARKED** (hold still, wait for fire).

During approach/docking, if the fire drifts past `REALIGN_THRESHOLD` it stops and re-centers, then resumes. Once any fire is seen the rover is **engaged** and tolerates a much longer loss (`ENGAGED_GRACE_S`) before giving up; only then does it scan, then free-roam.

#### Speed Tiers (`config.py` → `MotionCfg`)

| Constant | Value | Used for |
|----------|-------|---------|
| `align` | 50 | Centering turns (slow, precise) |
| `approach` | 200 | Fast forward toward fire (far out) |
| `approach_slow` | 80 | Forward in the final stretch before docking |
| `scan` | 80 | 360° step-scan spin |
| `idle` | 200 | Free-roam forward + avoidance turns |
| `dock` | 30 | Fwd/rev nudges while converging on the dock target |

#### Turn Timing — single calibration datum

All turn durations derive from **one** measured value via the linear model
`turn_ms(speed, deg) = TURN_90_MAX_MS · (255/speed) · (deg/90)` (helper
`turn_ms()` in `autonomy.py`). The rig datum is `turn_90_max_ms = 1200` ms —
a 90° pivot at full PWM (255), matching the firmware `TURN_MS=1200` /
"4800 tam tur" (360°). To re-calibrate, measure that one number; everything
else (align 6120 ms, idle 1530 ms, 180° 3060 ms, scan-step 1275 ms, extinguish
sweep steps) recomputes. `recorder.js` mirrors the same formula for its
dead-reckoning turn rate.

#### Alignment / Approach / Docking Tuning (`config.py` → `AutonomyCfg`)

| Constant | Value | Meaning |
|----------|-------|---------|
| `alignment_threshold` | 40 px | Dead-zone — within this = "centered" |
| `realign_threshold` | 80 px | Max drift during approach/dock before re-center |
| `camera_fov` | 55° | Horizontal field of view |
| `settle_time` | 0.35 s | Wait after turn before re-deciding |
| `min_turn_ms` | 60 ms | Minimum motor-on time for any turn |
| `fire_lost_grace` | 5.0 s | Fire absent this long (un-engaged) before search |
| `engaged_grace_s` | 12.0 s | Committed-fire leash before giving up |
| `pump_start_cm` | 20 cm | Front distance to STOP + PUMP_ON + start docking |
| `dock_commit_cm` | 20 cm | At/below this, docking ignores the camera and drives on the front sensor alone |
| `approach_slow_cm` | 50 cm | Front distance to drop fast→slow approach speed |
| `approach_timeout` | 8.0 s | Safety: abort approach if not docking |
| `dock_target_cm` | 10 cm | Closed-loop front-distance target before extinguish |
| `dock_tol_cm` | 2 cm | ± band around target counted as "docked" (8–12 cm) |
| `dock_nudge_ms` | 220 ms | Fwd/rev pulse length (longer = more ground per nudge) |
| `dock_settle_ms` | 120 ms | Stop/settle (sensor read) between nudges (kept short) |
| `dock_confirm_n` | 1 | In-band reads required to extinguish (reliable sensor) |
| `dock_timeout_s` | 12.0 s | Safety: extinguish at current range if not converged |

#### Stepped-Scan Tuning (`config.py` → `AutonomyCfg`)

| Constant | Value | Meaning |
|----------|-------|---------|
| `scan_step_deg` | 30° | Degrees turned per scan step (360/step = # of looks) |
| `scan_dwell_s` | 0.6 s | Time stopped per step so YOLO sees clean frames |

#### Free-Roam Tuning

| Constant | Value | Meaning |
|----------|-------|---------|
| `OBSTACLE_CM` | 30 cm | Front reading that counts as blocking |
| `SIDE_CM` | 30 cm | Side reading above which = "free to turn" |
| `ROAM_SCAN_INTERVAL` | 10.0 s | Seconds of clear driving before re-scan |

#### Extinguish choreography (`_EXT_SEQUENCE`)

`EXTINGUISHING` is a **fixed, sensor-free, uninterruptible** list of timed
steps `(action, duration_ms, speed)`, advanced one step per `update()` tick by
`_extinguish_tick()`. It plays to the end regardless of fire/sensor state. Three
phases, each a `L R R L L R R L` oscillating pump sweep that ends back at center:

| Phase | Pattern | Speed | Purpose |
|-------|---------|-------|---------|
| 1 | slow turn sweep | `_EXT_SPD_SLOW`=50 | wide low-speed coverage |
| 2 | fast turn sweep | `_EXT_SPD_FAST`=80 | faster coverage + final right-nudge correction |
| 3 | fwd/rev drive `F R R F F R R F` | `_EXT_SPD_DRIVE`=50 | sweep depth via forward/back |

Per-step turn time `_EXT_MS = (_EXT_DEG/90) * TURN_90_ALIGN_MS` with
`_EXT_DEG=15°` — the one value to tune on the rig. After phase 3 a
`_EXT_BACKOFF_MS`=1000 reverse backs the rover ≈10 cm off the fire so the
follow-up 360° re-scan starts clear, then the FSM enters PARKED.

#### State Machine

States: `IDLE`, `TURNING`, `SETTLING`, `APPROACH`, `DOCKING`, `EXTINGUISHING`,
`SCANNING`, `ROAMING`, `PARKED` (`ARRIVED` is a log-only label that immediately
enters EXTINGUISHING).

```
         ┌─────────────────────────────────────────────────────────────────┐
         │  FIRE PREEMPTION (checked every frame, highest priority)         │
         │  Fire seen while SCANNING / ROAMING / PARKED → abort → IDLE      │
         │  (EXTINGUISHING is exempt — it never preempts, runs to the end)  │
         └─────────────────────────────────────────────────────────────────┘

IDLE ──── no fire > grace (5s, or 12s if engaged) ──→ SCANNING (stepped)
  │                                                      │ 360° done, no fire
  │  fire off-center                                     ↓
  └─────────────────────→ TURNING                    ROAMING ←──────────────────┐
                              │ turn done                │ 10s clear             │
                              ↓                          │                       │
                          SETTLING                   360° re-scan            obstacle?
                              │ settled                  ↓                       │
                              ↓                       SCANNING               ROAMING (turn phase)
  fire centered, far ─────→ APPROACH                                             │ turn done
                              │ front ≤ 20cm → STOP                              └───────────────
                              ↓
                          DOCKING  ── front = 10±2cm ──→ EXTINGUISHING
                              │ (closed-loop fwd/rev nudges)      │ sequence complete
                              │                                   ↓ back-off + post-ext 360°
  fire centered + ≤20cm ──────────────────────────────────→ SCANNING ──→ PARKED
                                                                        │ fire returns
                                                                        └──→ IDLE
   (APPROACH/DOCKING: drift > 80px / fire lost / timeout → STOP → IDLE)
```

**Fire preemption rule:** when fire is present and state is SCANNING, ROAMING, or PARKED → forced back to IDLE immediately (with a STOP) to re-align this frame. No grace delay — fire detection is instant. **EXTINGUISHING is the one exception**: it is checked first and runs to completion no matter what.

**Stepped scan (`SCANNING`):** the 360° sweep is `SCAN_STEPS` discrete `turn → STOP → dwell` steps (not a continuous spin), so the camera is **held still** for `scan_dwell_s` each step and YOLO runs on motion-free frames. Detection during a dwell is caught by the preemption rule above.

**Engagement / grace:** once any fire is seen, `_engaged` is set. While engaged, a fire loss is tolerated for `ENGAGED_GRACE_S=12s` (vs `FIRE_LOST_GRACE=5s` un-engaged) before the FSM gives up and scans — so the rover "commits" to a spotted fire and doesn't abandon it on brief detection dropouts. `_engaged` clears on extinguish completion or when the long grace expires.

**Reliable docking (`DOCKING`):** entry sends `STOP` first and arms the pump only on the *next* tick (once fully halted) — this fixes the old slam where the rover coasted at `FWD,200` through the settle window. It then closed-loops onto `dock_target_cm ± dock_tol_cm` with **both forward and reverse** nudges, requiring `dock_confirm_n` consecutive in-band reads before extinguishing.

**Dock commit (camera blind-spot):** YOLO detection drops out at close range (the fire fills or leaves the frame), which used to make docking abandon back to IDLE on `has_fire == False`. Now, once the front sensor reads `≤ dock_commit_cm`, docking **latches committed** (`_dock_committed`) and stops consulting the camera entirely — no fire-loss or drift abort — driving on the reliable distance sensor to `dock_target_cm` and then extinguishing. Camera-based abandon/re-center only applies while *not yet* committed (i.e. when `dock_commit_cm < pump_start_cm`, for the outer slice of the dock). The `dock_timeout_s` safety still bounds the whole phase.

**Post-extinguish cool-down:** a 360° scan flagged `_scan_then_stop` ends in PARKED (not roam). PARKED holds still until fire returns, then preemption kicks it back to IDLE.

**Avoidance turn resets 10s scan timer** — clock restarts when the avoidance turn completes and forward driving resumes.

---

## Browser Dashboard (`pi_code/templates/` + `pi_code/static/`)

No build step. `index.html` is a thin HTML shell; all styling lives in
`static/css/dashboard.css` and behaviour is split across four JS modules loaded
in order: `ui.js` → `controls.js` → `map.js` → `recorder.js`. Flask serves
`/static/...` (configured in `web.py`). Opens via `http://<pi-ip>:5000`.

- **MJPEG stream** — `/video_feed` endpoint, YOLOv8 bounding boxes drawn server-side
- **WebSocket events** received (`ui.js`):
  - `sensor` — left/center/right distances + flame ADC + flame digital
  - `fire_yolo` — detected bool, count, cx, cy, deviation px, confidence
  - `log` — timestamped log lines with CSS class (`info` / `warn` / `fire` / `cmd` / `pump`)
  - `mode_changed` — `{manual}`, syncs the toggle to server mode (`controls.js`)
- **WebSocket events** sent:
  - `command` — `{cmd, speed}` for motion, `{cmd}` for STOP/pump
  - `set_mode` — `{manual}` to switch manual/auto
- **Manual/Auto toggle** — when AUTO, the Motor Controls card is locked (`auto-locked`)
- **Keyboard shortcuts** — Arrow keys = FWD/REV/LEFT/RIGHT, Space = STOP (manual only)
- **Speed slider** — 0–255, applied to all manual motion commands

### Run Report (`recorder.js` + `map.js`)

A **Start/End Run** recorder that reconstructs the rover's path client-side and
produces a post-run report overlay:

- **Dead-reckoning** — turns serial commands (parsed from `log` events) into an
  `(x, y, heading)` track using turn-rate / forward-speed constants derived from
  the `autonomy.py` durations. `DR_FWD_CMS` is a **placeholder — calibrate on the rig**.
- **Semantic event detection** — scans log/fire/sensor events to count fires,
  extinguish (PUMP_ON) events, obstacles (`⛔`), and 360° scans, and to drop map
  markers (start/end/fire/arrived/extinguish/obstacle/scan).
- **Report overlay** — travel-map canvas (grid, path, north arrow, scale bar,
  hover tooltips), run-summary stats grid, and an event timeline.
- **Export** — `Export JSON` (full event log + markers + path) and `Export Map PNG`.

> The map is a dead-reckoning estimate from command timing, **not** measured
> odometry — accuracy depends on the rig-calibrated speed/turn constants.

---

## Development Tools

### `pi_code/test/command_sender.py`

Interactive CLI for manual rover control. Accepts shorthand (`f`, `l`, `r`, `s`) and full command names with optional speed (`fwd 150`). Auto-detects serial port; override with first argv.

### `pi_code/test/sensor_monitor.py`

Read-only sensor readout. Parses `D,...` lines from Arduino and prints formatted table. Useful for verifying sonar and flame sensor readings before running autonomy.

### `pi_code/test/extinguish_test.py`

Forces the `Aligner` FSM into `EXTINGUISHING` (`_start_extinguish()`) and drives
its `update()` loop at 30 Hz against the **real Arduino** — the exact production
code path. Gives an 8 s startup countdown to position the rover in front of the
fire, then plays the full choreography. Tune the `_EXT_*` constants in
`autonomy.py`, re-run, repeat. Run from `pi_code/`; pass a port as `argv[1]` to
override auto-detect.

---

## Deployment

```bash
# Copy to Pi (whole package + launcher + templates + static assets)
scp -r pi_code/run.py pi_code/rover pi_code/templates pi_code/static pi_code/models \
    mertergorun@172.20.10.2:~/fire_dashboard/

# Install Python dependencies on Pi
pip install ultralytics opencv-python flask flask-socketio pyserial huggingface_hub

# Run (from the dir containing run.py + rover/)
cd ~/fire_dashboard && python3 run.py

# Run without YOLO (sensor + manual control only)
python3 run.py --no-yolo

# Run without autonomous alignment (observe only)
python3 run.py --no-align

# Force specific serial port
python3 run.py --serial /dev/ttyUSB0
```

---

## YOLO Model

- Architecture: YOLOv8
- Source: `SalahALHaismawi/yolov26-fire-detection` (HuggingFace)
- Local path: `pi_code/models/best.pt`
- Inference size: 256×256 (Pi-safe; 320+ causes OOM/crash on Pi)
- Tracked labels: `fire` only — all other classes ignored
- Frame skip: runs every 5th frame, cached result drawn on all frames
