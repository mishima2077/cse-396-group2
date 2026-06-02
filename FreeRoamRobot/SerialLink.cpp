// ===== SerialLink.cpp =====
#include "SerialLink.h"

void SerialLink::update(PiCommand& cmd) {
    cmd.fresh = false;
    while (Serial.available() > 0) {
        char c = (char)Serial.read();
        if (c == '\n' || c == '\r') {
            if (idx_ > 0) { buf_[idx_] = '\0'; parseLine(buf_, cmd); idx_ = 0; }
        } else if (idx_ < SERIAL_BUF_LEN - 1) {
            buf_[idx_++] = c;
        } else {
            idx_ = 0;  // taşma → satırı at
        }
    }
}

void SerialLink::parseLine(char* line, PiCommand& cmd) {
    CmdType t   = CMD_NONE;
    uint8_t spd = 0;

    if      (strcmp(line, "STOP")     == 0) { t = CMD_STOP; }
    else if (strcmp(line, "PUMP_ON")  == 0) { t = CMD_PUMP_ON; }
    else if (strcmp(line, "PUMP_OFF") == 0) { t = CMD_PUMP_OFF; }
    else if (strcmp(line, "ROAM")     == 0) { t = CMD_ROAM; }
    else if (strncmp(line, "FORWARD,",    8)  == 0) { t = CMD_FORWARD;    spd = (uint8_t)atoi(line + 8); }
    else if (strncmp(line, "REVERSE,",    8)  == 0) { t = CMD_REVERSE;    spd = (uint8_t)atoi(line + 8); }
    else if (strncmp(line, "TURN_LEFT,",  10) == 0) { t = CMD_TURN_LEFT;  spd = (uint8_t)atoi(line + 10); }
    else if (strncmp(line, "TURN_RIGHT,", 11) == 0) { t = CMD_TURN_RIGHT; spd = (uint8_t)atoi(line + 11); }
    else { return; }  // bilinmeyen → ignore

    cmd.type      = t;
    cmd.speed     = spd;
    cmd.fresh     = true;
    cmd.lastCmdMs = millis();
}

void SerialLink::reportSensors(uint16_t L, uint16_t C, uint16_t R, uint16_t flameRaw) {
    unsigned long now = millis();
    if (now - tSonar_ >= SONAR_REPORT_MS) {
        Serial.print(F("SONAR,"));
        Serial.print(L);   Serial.print(',');
        Serial.print(C);   Serial.print(',');
        Serial.println(R);
        tSonar_ = now;
    }
    if (now - tFlame_ >= FLAME_REPORT_MS) {
        Serial.print(F("FLAME,"));
        Serial.println(flameRaw);
        tFlame_ = now;
    }
}
