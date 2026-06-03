#include <string.h>
#include <stdlib.h>
#include "Commands.h"
#include "Motors.h"
#include "water_pump.h"

bool command_execute(const char* cmd) {
    if (!cmd || strlen(cmd) == 0) {
        return false;
    }

    // Helper: extract speed from "CMD,SPEED" format
    auto get_speed = [](const char* s) -> uint8_t {
        const char* comma = strchr(s, ',');
        if (comma) {
            return (uint8_t)constrain(atoi(comma + 1), 0, 255);
        }
        return 0;
    };

    // Compare commands (case-insensitive)
    if (strncmp(cmd, "FWD", 3) == 0 || strcmp(cmd, "FORWARD") == 0) {
        forward(get_speed(cmd));
        return true;
    }

    if (strncmp(cmd, "REV", 3) == 0 || strcmp(cmd, "REVERSE") == 0) {
        reverse(get_speed(cmd));
        return true;
    }

    if (strncmp(cmd, "TURN_L", 6) == 0 || strcmp(cmd, "LEFT") == 0) {
        turn_left(get_speed(cmd));
        return true;
    }

    if (strncmp(cmd, "TURN_R", 6) == 0 || strcmp(cmd, "RIGHT") == 0) {
        turn_right(get_speed(cmd));
        return true;
    }

    if (strcmp(cmd, "STOP") == 0) {
        stop();
        return true;
    }

    if (strcmp(cmd, "PUMP_ON") == 0) {
        pump_on();
        return true;
    }

    if (strcmp(cmd, "PUMP_OFF") == 0) {
        pump_off();
        return true;
    }

    return false;
}
