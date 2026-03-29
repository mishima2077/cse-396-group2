#ifndef MODULE_SYSTEM_TEST_H
#define MODULE_SYSTEM_TEST_H

/**
 * @file module_system_test.h
 * @brief Integration/Test (MOD-08) – public interface
 * @author Ayşe Feyza SERBEST - 220104004052
 *         Görkem UYSAL - 230104004174
 * @date 2026-03-29
 * @version 0.2
 *
 * Changelog:
 * v0.1 - Initial test functions
 * v0.2 - Added test modes, report system, simulation control
 */

#include <stdint.h>
#include "../MOD 02/flame_detection.h"

/* ---------- TEST STATUS ---------- */
typedef enum {
    TEST_OK = 0,
    TEST_FAIL_SENSOR,
    TEST_FAIL_DISTANCE,
    TEST_FAIL_MOTOR,
    TEST_FAIL_PUMP
} test_status_t;

/* ---------- TEST MODE ---------- */
typedef enum {
    TEST_MODE_REAL = 0,
    TEST_MODE_SIMULATION
} test_mode_t;

/* ---------- TEST REPORT ---------- */
typedef struct {
    int sensor_ok;
    int distance_ok;
    int motor_ok;
    int pump_ok;
} test_report_t;

/* ---------- SIMULATION INPUT ---------- */
typedef struct {
    flame_data_t flame_data;
    uint16_t distance_cm;
} test_simulation_input_t;

/* ---------- API ---------- */

/** Initialize test module */
void test_init(void);

/** Set test mode (real / simulation) */
void test_set_mode(test_mode_t mode);

/** Run full system self-check */
test_status_t test_run_self_check(void);

/** Get detailed test report */
void test_get_report(test_report_t *report);

/** Set simulation data */
void test_set_simulation_data(const test_simulation_input_t *data);

/** Periodic test update (optional monitoring) */
void test_update(void);

#endif /* MODULE_SYSTEM_TEST_H */