// ===== SlaveController.h =====
// Arduino tamamen Pi'nin komut kölesi.
// Tüm navigasyon ve ateş misyonu mantığı Pi'de.
// Bu sınıf: gelen komutu al → motoru/pompayı çalıştır.
// Pi susarsa SLAVE_TIMEOUT_MS sonra dur.
#ifndef SLAVE_CONTROLLER_H
#define SLAVE_CONTROLLER_H

#include <Arduino.h>
#include "Config.h"
#include "SkidSteerMotors.h"
#include "WaterPump.h"
#include "SerialLink.h"

class SlaveController {
public:
    void begin(SkidSteerMotors* m, WaterPump* p);
    void update(PiCommand& cmd);

private:
    SkidSteerMotors* motors_ = nullptr;
    WaterPump*       pump_   = nullptr;
};

#endif
