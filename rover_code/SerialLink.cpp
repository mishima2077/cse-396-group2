#include <Arduino.h>
#include "SerialLink.h"

void SerialLink::begin(unsigned long baud) {
    Serial.begin(baud);
    rx_index = 0;
}

void SerialLink::sendSensors(const SensorData& data) {
    Serial.print('D');
    Serial.print(',');
    Serial.print(data.distance_left);
    Serial.print(',');
    Serial.print(data.distance_center);
    Serial.print(',');
    Serial.print(data.distance_right);
    Serial.print(',');
    Serial.print(data.flame_analog);
    Serial.print(',');
    Serial.print(data.flame_digital);
    Serial.print('\n');
}

bool SerialLink::receiveCommand(char* buffer, uint8_t max_len) {
    while (Serial.available() > 0) {
        char c = Serial.read();

        if (c == '\n') {
            if (rx_index > 0) {
                rx_buffer[rx_index] = '\0';
                strncpy(buffer, rx_buffer, max_len - 1);
                buffer[max_len - 1] = '\0';
                rx_index = 0;
                return true;
            }
            rx_index = 0;
            continue;
        }

        if (c == '\r') {
            continue;
        }

        if (rx_index < BUFFER_SIZE - 1) {
            rx_buffer[rx_index++] = c;
        }
    }

    return false;
}
