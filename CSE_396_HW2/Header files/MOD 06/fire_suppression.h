#ifndef FIRE_SUPPRESSION_H
#define FIRE_SUPPRESSION_H

/**
 * @file    fire_suppression.h
 * @brief   Suppression Hardware Module (MOD-06) – public interface
 * @author  Mehmet Alp ATAY - 220104004020
 *          Adil Mert ERGÖRÜN - 220104004048
 * @date    2026-03-28
 * @version 0.1
 *
 * Changelog:
 *   v0.1 (2026-03-28) – Initial draft: suppression_init, suppression_activate,
 *                        suppression_deactivate, suppression_is_active, data types
 */

#include <stdint.h>

/* ---------------------------------------------------------------
 * Constants & Macros
 * --------------------------------------------------------------- */

/** Default pump burst duration in milliseconds. */
#define SUPPRESSION_PUMP_DURATION_MS  3000

/** Minimum time between consecutive activations (relay cooldown) in ms. */
#define SUPPRESSION_COOLDOWN_MS       500

/** GPIO pin number connected to relay IN signal (adjust per board). */
#define SUPPRESSION_RELAY_PIN         7

/* ---------------------------------------------------------------
 * Data Types
 * --------------------------------------------------------------- */

/**
 * @brief Return / error codes for the fire suppression module.
 */
typedef enum {
    SUPPRESSION_OK             =  0,  /**< Operation successful */
    SUPPRESSION_ERR_INIT       = -1,  /**< Hardware initialisation failed */
    SUPPRESSION_ERR_COOLDOWN   = -2,  /**< Activation denied – cooldown active */
    SUPPRESSION_ERR_HARDWARE   = -4   /**< Relay or pump hardware fault */
} suppression_status_t;

/**
 * @brief Snapshot of the suppression subsystem state.
 */
typedef struct {
    uint8_t  is_active;          /**< Non-zero while pump is running */
    uint32_t last_activated_ms;  /**< Timestamp of last activation (ms since boot) */
    uint32_t total_activations;  /**< Cumulative number of pump activations */
} suppression_state_t;

/**
 * @brief Command structure sent from Control & Decision module (MOD-4).
 */
typedef struct {
    uint8_t  activate;       /**< 1 = activate pump, 0 = deactivate */
    uint16_t duration_ms;    /**< Override pump duration (0 = use default) */
    uint32_t issued_at_ms;   /**< Timestamp command was issued */
} suppression_cmd_t;

/* ---------------------------------------------------------------
 * Public Functions
 * --------------------------------------------------------------- */

/**
 * @brief  Initialise relay GPIO and pump hardware.
 * @return SUPPRESSION_OK on success, SUPPRESSION_ERR_INIT on failure.
 */
suppression_status_t suppression_init(void);

/**
 * @brief  Activate the water pump for the specified duration.
 * @param  duration_ms  Pump-on time in ms; pass 0 to use SUPPRESSION_PUMP_DURATION_MS.
 * @return SUPPRESSION_OK on success, or an error code if activation is denied.
 */
suppression_status_t suppression_activate(uint16_t duration_ms);

/**
 * @brief  Immediately deactivate the pump and open the relay.
 * @return SUPPRESSION_OK on success, SUPPRESSION_ERR_HARDWARE if relay fails to open.
 */
suppression_status_t suppression_deactivate(void);

/**
 * @brief  Query whether the pump is currently running.
 * @return 1 if active, 0 if idle.
 */
uint8_t suppression_is_active(void);

/**
 * @brief  Fill a caller-owned struct with the current module state.
 * @param  out  Pointer to a suppression_state_t to populate.
 * @return SUPPRESSION_OK on success.
 */
suppression_status_t suppression_get_state(suppression_state_t *out);

/**
 * @brief  Apply a command issued by the Control & Decision module.
 * @param  cmd  Pointer to a suppression_cmd_t describing the desired action.
 * @return SUPPRESSION_OK on success, error code otherwise.
 */
suppression_status_t suppression_apply_cmd(const suppression_cmd_t *cmd);

/**
 * @brief  Power down the relay and release hardware resources.
 */
void suppression_stop(void);

#endif /* FIRE_SUPPRESSION_H */
