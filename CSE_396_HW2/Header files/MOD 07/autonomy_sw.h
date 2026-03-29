/**
 * @file autonomy_sw.h
 * @brief Central Finite State Machine and system decision logic.
 * @author Ayşe Feyza SERBEST ([ID])
 * @date 2026-03-28
 * @version 0.1
 */

#ifndef MODULE_AUTONOMY_SW_H
#define MODULE_AUTONOMY_SW_H

typedef enum {
    STATE_SEARCH = 0,
    STATE_DETECT,
    STATE_APPROACH,
    STATE_STOP,
    STATE_EXTINGUISH,
    STATE_VERIFY
} autonomy_state_t;

/**
 * @brief Main tick function that evaluates sensor data and transitions states.
 */
void autonomy_update(void);

/**
 * @brief Returns the current system state for debugging/monitoring.
 */
autonomy_state_t autonomy_get_current_state(void);

#endif /* MODULE_AUTONOMY_SW_H */