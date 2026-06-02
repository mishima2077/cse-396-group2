// ===== SerialLink.h =====
#ifndef SERIAL_LINK_H
#define SERIAL_LINK_H

#include <Arduino.h>
#include "Config.h"

// Pi → Arduino komut tipleri
enum CmdType : uint8_t {
    CMD_NONE       = 0,
    CMD_STOP,
    CMD_FORWARD,     // FORWARD,<speed>
    CMD_REVERSE,     // REVERSE,<speed>
    CMD_TURN_LEFT,   // TURN_LEFT,<speed>
    CMD_TURN_RIGHT,  // TURN_RIGHT,<speed>
    CMD_PUMP_ON,
    CMD_PUMP_OFF,
    CMD_ROAM         // free-roam'a geri dön
};

struct PiCommand {
    CmdType       type      = CMD_NONE;
    uint8_t       speed     = 0;
    bool          fresh     = false;        // bu loop'ta yeni komut geldi
    unsigned long lastCmdMs = 0;            // son komutun millis() zamanı
};

class SerialLink {
public:
    void begin() { Serial.begin(SERIAL_BAUD); idx_ = 0; tSonar_ = 0; tFlame_ = 0; }
    // Pi'den gelen komutları non-blocking parse eder
    void update(PiCommand& cmd);
    // Arduino → Pi sensör raporu (her loop'ta çağır)
    void reportSensors(uint16_t L, uint16_t C, uint16_t R, uint16_t flameRaw);

private:
    void parseLine(char* line, PiCommand& cmd);
    char          buf_[SERIAL_BUF_LEN];
    uint8_t       idx_;
    unsigned long tSonar_;
    unsigned long tFlame_;
};

#endif
