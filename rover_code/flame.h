#ifndef FLAME_H
#define FLAME_H

#include <stdint.h>

#define FLAME_SENSOR_COUNT  3
#define FLAME_DO_PINS       {2, 3, 4}
#define FLAME_AO_PINS       {A0, A1, A2}

void flame_init(void);
void flame_read(uint16_t *values);
void flame_detected(bool *results);

#endif
