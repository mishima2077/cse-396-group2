#include <string.h>
#include "Commands.h"
#include "Motors.h"
#include "water_pump.h"

bool command_execute(const char* cmd) {
    if (!cmd || strlen(cmd) == 0) {
        return false;
    }

    // Compare commands (case-insensitive)
    if (strncmp(cmd, "FWD", 3) == 0 || strcmp(cmd, "FORWARD") == 0) {
        forward();
        return true;
    }

    if (strncmp(cmd, "REV", 3) == 0 || strcmp(cmd, "REVERSE") == 0) {
        reverse();
        return true;
    }

    if (strncmp(cmd, "TURN_L", 6) == 0 || strcmp(cmd, "LEFT") == 0) {
        turn_left();
        return true;
    }

    if (strncmp(cmd, "TURN_R", 6) == 0 || strcmp(cmd, "RIGHT") == 0) {
        turn_right();
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
