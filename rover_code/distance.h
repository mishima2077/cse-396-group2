#ifndef DISTANCE_H
#define DISTANCE_H

#include <stdint.h>

#define DIST_TRIG_PIN  9
#define DIST_ECHO_PIN  10

void     distance_init(void);
uint16_t distance_read_cm(void);

#endif
