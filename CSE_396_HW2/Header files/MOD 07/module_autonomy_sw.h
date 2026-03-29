#ifndef MODULE_AUTONOMY_SW_H
#define MODULE_AUTONOMY_SW_H

/**
 * @file module_autonomy_sw.h
 * @brief Central FSM and decision logic
 * @version 0.2
 * @author Ayşe Feyza SERBEST 220104004052
 * @date 2026-03-29
 *
 * Changelog:
 * v0.1 - Initial version
 * v0.2 - Added input/output structs and init/reset
 */

#include <stdint.h>

/* ---------- STATE ---------- */
typedef enum {
    STATE_SEARCH = 0,
    STATE_DETECT,
    STATE_APPROACH,
    STATE_AVOID_OBSTACLE,
    STATE_STOP,
    STATE_EXTINGUISH,
    STATE_VERIFY
} autonomy_state_t;

/* ---------- INPUT ---------- */
typedef struct {
    int flame_dir;          // LEFT / CENTER / RIGHT
    uint16_t distance_cm;
    int flame_detected;
} autonomy_input_t;

/* ---------- OUTPUT ---------- */
typedef struct {
    int motion_cmd;         // FORWARD / TURN etc.
    int speed;
    int pump_on;
} autonomy_output_t;

/* ---------- API ---------- */

/** Initialize FSM */
void autonomy_init(void);

/** Main FSM update */
void autonomy_update(const autonomy_input_t *in);

/** Get current output commands */
void autonomy_get_output(autonomy_output_t *out);

/** Get current state */
autonomy_state_t autonomy_get_current_state(void);

/** Reset FSM */
void autonomy_reset(void);

/** Debug helper */
const char* autonomy_state_to_string(autonomy_state_t state);

#endif