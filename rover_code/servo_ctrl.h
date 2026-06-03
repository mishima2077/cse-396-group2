#ifndef SERVO_CTRL_H
#define SERVO_CTRL_H

#include <stdint.h>

void servo_init(void);
void servo_set(uint8_t angle);
uint8_t servo_get(void);

#endif // SERVO_CTRL_H
