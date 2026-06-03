#ifndef DISTANCE_H
#define DISTANCE_H

#include <stdint.h>
#include "Config.h"

void distance_init(void);
void distance_update(void);
uint16_t distance_get_left(void);
uint16_t distance_get_center(void);
uint16_t distance_get_right(void);

#endif
