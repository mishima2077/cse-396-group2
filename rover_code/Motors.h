#ifndef MOTORS_H
#define MOTORS_H

#include "Config.h"

void motors_init(void);

// Individual motor control
void left_forward(uint8_t speed);
void left_reverse(uint8_t speed);
void right_forward(uint8_t speed);
void right_reverse(uint8_t speed);

// Combined movement
void forward(uint8_t speed);
void reverse(uint8_t speed);
void turn_left(uint8_t speed);
void turn_right(uint8_t speed);
void stop(void);

#endif // MOTORS_H
