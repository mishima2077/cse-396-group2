/**
 * @file motion_control.h
 * @brief Motion Control SW (MOD-04) – public interface
 * @author Ahmet Halil YAMLI - 220104004957
 *         Derya UYSAL - 220104004045
 * @date 2026-03-28
 * @version 0.1
 *
 * Changelog:
 * v0.1 (2026-03-28)
 * - Initial draft with basic movement logic and differential drive support.
 */

#ifndef MODULE_MOTION_CONTROL_H
#define MODULE_MOTION_CONTROL_H

#include <stdint.h>
#include "../MOD 03/locomotion_hw.h"

/* -- Constants ----------------------------------------------------------- */

/** @brief Default motor speed (0-255 PWM) */
#define MOTION_DEFAULT_SPEED 150

/** @brief Minimum PWM value required to overcome static friction */
#define MOTION_MIN_THRESHOLD LOCO_HW_MIN_PWM

/* -- Data Types ---------------------------------------------------------- */

/** * @brief Operational status of the motion module
 */
typedef enum
{
    MOTION_OK = 0,          /**< Module operating normally */
    MOTION_ERR_DRIVER = -1, /**< Motor driver communication error */
    MOTION_ERR_PARAM = -2   /**< Invalid speed or direction parameter */
} motion_status_t;

/** * @brief Available movement directions for the differential drive
 */
typedef enum
{
    MOTION_DIR_STOP = 0,
    MOTION_DIR_FORWARD,
    MOTION_DIR_BACKWARD,
    MOTION_DIR_LEFT,
    MOTION_DIR_RIGHT
} motion_direction_t;

/** * @brief Current state of the locomotion system
 */
typedef struct
{
    motion_direction_t current_direction; /**< Active movement vector */
    uint8_t speed_left;                   /**< PWM value for left motors */
    uint8_t speed_right;                  /**< PWM value for right motors */
    uint32_t last_command_time;           /**< Timestamp of last valid command */
} motion_state_t;

/* -- Public Functions ---------------------------------------------------- */

/**
 * @brief Initialize motor driver pins and PWM channels.
 * @return MOTION_OK on success, error code otherwise.
 */
motion_status_t motion_init(void);

/**
 * @brief Execute a basic movement command.
 * @param dir The desired direction (Forward, Backward, Turn).
 * @param speed PWM intensity (0-255).
 * @return MOTION_OK if command was dispatched successfully.
 */
motion_status_t motion_drive(motion_direction_t dir, uint8_t speed);

/**
 * @brief Control left and right motors independently for custom maneuvers.
 * @param left_speed PWM value for left side (-255 to 255).
 * @param right_speed PWM value for right side (-255 to 255).
 * @return MOTION_OK on success.
 */
motion_status_t motion_set_differential(int16_t left_speed, int16_t right_speed);

/**
 * @brief Read the current state of the locomotion system.
 * @param out_state Pointer to a caller-owned motion_state_t struct.
 */
void motion_get_state(motion_state_t *out_state);

/**
 * @brief Immediate stop of all motor activity.
 */
void motion_emergency_stop(void);

#endif /* MODULE_MOTION_CONTROL_H */
