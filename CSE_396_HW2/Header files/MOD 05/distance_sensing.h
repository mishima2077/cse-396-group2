/**
 * @file distance_sensing.h
 * @brief Interface for HC-SR04 ultrasonic sensor and threshold detection.
 * @author Ahmet Halil Y., Derya U.
 * @date 2026-03-28
 * @version 0.1
 */

#ifndef MODULE_DISTANCE_SENSING_H
#define MODULE_DISTANCE_SENSING_H

#include <stdint.h>

#define DIST_SAFE_THRESHOLD_CM 15

typedef struct
{
    uint16_t distance_cm;
    uint32_t timestamp;
} dist_reading_t;

/**
 * @brief Initializes trigger and echo pins.
 */
int distance_init(void);

/**
 * @brief Performs an ultrasonic ping and returns distance in cm.
 */
uint16_t distance_read_cm(void);

/**
 * @brief Returns 1 if an obstacle is within the safe stopping threshold.
 */
int distance_is_unsafe(void);

#endif /* MODULE_DISTANCE_SENSING_H */
