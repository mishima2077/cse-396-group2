#ifndef MOTORS_H
#define MOTORS_H

#include "Config.h"

void motors_init(void);

// Individual motor control
void left_forward(void);
void left_reverse(void);
void right_forward(void);
void right_reverse(void);

// Combined movement
void forward(void);
void reverse(void);
void turn_left(void);
void turn_right(void);
void stop(void);

#endif // MOTORS_H
