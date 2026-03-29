/**
 * @file locomotion_hw.h
 * @brief Locomotion HW (MOD-03) – public interface
 * @author Cemal GÜMÜŞ - 210104004304
 *         Melih KAZANCI - 230104004909
 * @date 2026-03-28
 * @version 0.1
 *
 * Changelog:
 * v0.1 (2026-03-28)
 * - Initial draft; defined pin-level control functions for L298N integration.
 */

#ifndef MODULE_LOCOMOTION_HW_H
#define MODULE_LOCOMOTION_HW_H

#include <stdint.h>
#include <stdbool.h>

/* -- Constants & Macros -------------------------------------------------- */

/** @brief Maximum PWM duty cycle value for motor speed */
#define LOCO_HW_MAX_PWM 255

/** @brief Minimum PWM duty cycle to initiate movement */
#define LOCO_HW_MIN_PWM 60

/* -- Data Types ---------------------------------------------------------- */

/** * @brief Status codes for locomotion hardware operations.
 */
typedef enum {
    LOCO_HW_OK = 0,         /**< Hardware initialized and responding */
    LOCO_HW_ERR_CONFIG = -1, /**< GPIO or PWM configuration failure */
    LOCO_HW_ERR_VOLTAGE = -2 /**< Battery voltage below safe threshold */
} loco_hw_status_t;

/**
 * @brief Identifies the physical side of the rover drive system.
 */
typedef enum {
    LOCO_HW_LEFT = 0,
    LOCO_HW_RIGHT = 1
} loco_hw_side_t;

/* -- Public Function Declarations ---------------------------------------- */

/**
 * @brief Configures GPIO pins and PWM timers for the motor driver.
 * @return LOCO_HW_OK on successful initialization.
 */
loco_hw_status_t loco_hw_init(void);

/**
 * @brief Sets raw PWM and direction for a specific motor side.
 * @param side The motor side to control (LEFT or RIGHT).
 * @param pwm_value Duty cycle (0 to LOCO_HW_MAX_PWM).
 * @param forward True for clockwise, false for counter-clockwise.
 * @return LOCO_HW_OK on success.
 */
loco_hw_status_t loco_hw_set_motor(loco_hw_side_t side, uint8_t pwm_value, bool forward);

/**
 * @brief Disables PWM output to both motors immediately (Coast).
 */
void loco_hw_disable_motors(void);

/**
 * @brief Actively brakes the motors by pulling driver pins to a common state.
 */
void loco_hw_brake(void);

/**
 * @brief Checks if the battery level is sufficient for motor operation.
 * @return True if voltage is within operating range, false otherwise.
 */
bool loco_hw_is_power_stable(void);

#endif /* MODULE_LOCOMOTION_HW_H */