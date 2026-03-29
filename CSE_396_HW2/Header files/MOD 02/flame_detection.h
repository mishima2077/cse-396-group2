#ifndef FLAME_DETECTION_H
#define FLAME_DETECTION_H

/**
 * @file    flame_detection.h
 * @brief   Flame Detection Module – public interface
 * @author  Adil Mert Ergörün - 220104004048
 *          Mehmet Alp Atay - 220104004020
 * @date    2026-03-28
 * @version 0.1
 *
 * Changelog:
 *   v0.1 (2026-03-28) – Initial draft: flame_init, flame_read,
 *                        flame_get_direction, flame_stop, data types
 */

#include <stdint.h>

/* ---------------------------------------------------------------
 * Constants & Macros
 * --------------------------------------------------------------- */

/** Number of IR flame sensor modules on the rover front. */
#define FLAME_SENSOR_COUNT       3

/** ADC threshold above which a sensor is considered to detect flame. */
#define FLAME_THRESHOLD          500

/** Sampling interval in milliseconds. */
#define FLAME_SAMPLE_INTERVAL_MS 50

/** Maximum raw ADC reading (10-bit ADC on Arduino/ESP32). */
#define FLAME_ADC_MAX            1023

/* ---------------------------------------------------------------
 * Data Types
 * --------------------------------------------------------------- */

/**
 * @brief Return / error codes for the flame detection module.
 */
typedef enum {
    FLAME_OK            =  0,  /**< Operation successful */
    FLAME_ERR_INIT      = -1,  /**< Hardware initialisation failed */
    FLAME_ERR_NO_SENSOR = -2,  /**< One or more sensors not responding */
    FLAME_ERR_TIMEOUT   = -3   /**< Read operation timed out */
} flame_status_t;

/**
 * @brief Detected flame direction relative to the rover.
 */
typedef enum {
    FLAME_DIR_NONE   = 0,  /**< No flame detected */
    FLAME_DIR_LEFT   = 1,  /**< Flame to the left */
    FLAME_DIR_CENTER = 2,  /**< Flame directly ahead */
    FLAME_DIR_RIGHT  = 3   /**< Flame to the right */
} flame_direction_t;

/**
 * @brief Aggregated data from all three flame sensors.
 */
typedef struct {
    uint16_t          raw[FLAME_SENSOR_COUNT]; /**< Raw ADC values [left, center, right] */
    uint16_t          max_intensity;           /**< The highest ADC reading of the three (proxy for distance) */
    uint8_t           detected;                /**< Non-zero if max_intensity > FLAME_THRESHOLD */
    flame_direction_t direction;               /**< Dominant flame direction */
    uint32_t          timestamp_ms;            /**< Time of reading (ms since boot) */
} flame_data_t;

/* ---------------------------------------------------------------
 * Callback Type
 * --------------------------------------------------------------- */

/**
 * @brief Callback invoked on every new flame reading.
 * @param data  Pointer to the freshly sampled flame_data_t (read-only).
 */
typedef void (*flame_cb_t)(const flame_data_t *data);

/* ---------------------------------------------------------------
 * Public Functions
 * --------------------------------------------------------------- */

/**
 * @brief  Initialise flame sensor hardware and GPIO pins.
 * @return FLAME_OK on success, FLAME_ERR_INIT on failure.
 */
flame_status_t flame_init(void);

/**
 * @brief  Start periodic flame sampling at FLAME_SAMPLE_INTERVAL_MS.
 * @param  cb  Optional callback invoked on each sample (pass NULL to disable).
 * @return FLAME_OK on success.
 */
flame_status_t flame_start(flame_cb_t cb);

/**
 * @brief  Read the latest sensor data synchronously.
 * @param  out  Caller-owned pointer to a flame_data_t struct to populate.
 * @return FLAME_OK on success, FLAME_ERR_TIMEOUT if no data is available.
 */
flame_status_t flame_read(flame_data_t *out);

/**
 * @brief  Query the current dominant flame direction without a full read.
 * @return One of the flame_direction_t enum values.
 */
flame_direction_t flame_get_direction(void);

/**
 * @brief  Stop sampling and power down sensor peripherals.
 */
void flame_stop(void);

#endif /* FLAME_DETECTION_H */
