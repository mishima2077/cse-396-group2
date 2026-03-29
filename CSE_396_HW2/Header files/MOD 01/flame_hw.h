/**
 * @file flame_hw.h
 * @brief Flame Sensing HW (MOD-01) – public interface
 * @author Cemal GÜMÜŞ - 210104004304
 *         Melih KAZANCI - 230104004909
 * @date 2026-03-28
 * @version 0.1
 */

#ifndef MODULE_FLAME_HW_H
#define MODULE_FLAME_HW_H

#include <stdint.h>

#define FLAME_HW_SENSOR_COUNT 3
#define FLAME_HW_THRESHOLD_DEFAULT 500

typedef enum {
    FLAME_HW_OK = 0,
    FLAME_HW_ERR_ADC = -1
} flame_hw_status_t;

/**
 * @brief Initialize flame sensor pins (ADC configuration).
 */
flame_hw_status_t flame_hw_init(void);

/**
 * @brief Reads raw ADC values from all sensors.
 * @param buffer Array of size FLAME_HW_SENSOR_COUNT.
 */
void flame_hw_read_raw(uint16_t *buffer);

#endif /* MODULE_FLAME_HW_H */