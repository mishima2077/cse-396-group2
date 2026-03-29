/**
 * @file system_test.h
 * @brief Validation and end-to-end testing routines.
 * @author Ayşe Feyza SERBEST ([ID])
 * @date 2026-03-28
 * @version 0.1
 */

#ifndef MODULE_SYSTEM_TEST_H
#define MODULE_SYSTEM_TEST_H

/**
 * @brief Executes a self-test of all hardware submodules.
 * @return 1 if all modules pass, 0 otherwise.
 */
int test_run_self_check(void);

/**
 * @brief Simulates a fire detection event for verification.
 */
void test_simulate_fire_event(void);

#endif /* MODULE_SYSTEM_TEST_H */