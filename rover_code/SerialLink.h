#ifndef SERIALLINK_H
#define SERIALLINK_H

#include <stdint.h>
#include "Protocol.h"

class SerialLink {
public:
    void begin(unsigned long baud = 115200UL);
    void sendSensors(const SensorData& data);
    bool receiveCommand(char* buffer, uint8_t max_len);

private:
    static constexpr uint8_t BUFFER_SIZE = 32;
    char rx_buffer[BUFFER_SIZE];
    uint8_t rx_index;
};

#endif // SERIALLINK_H
