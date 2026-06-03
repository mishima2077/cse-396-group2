#ifndef FLAME_H
#define FLAME_H

#include <stdint.h>
#include "Config.h"

void flame_init(void);
void flame_update(void);
uint16_t flame_get_analog(void);
uint8_t flame_get_digital(void);

#endif
