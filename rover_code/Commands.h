#ifndef COMMANDS_H
#define COMMANDS_H

#include <stdbool.h>

// Parse and execute a command from Raspberry Pi
// Returns true if command was recognized and executed
bool command_execute(const char* cmd);

#endif // COMMANDS_H
