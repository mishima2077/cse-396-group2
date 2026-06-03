#include "Config.h"
#include "Protocol.h"
#include "SerialLink.h"
#include "distance.h"
#include "flame.h"
#include "water_pump.h"
#include "Motors.h"
#include "Commands.h"

SerialLink link;
SensorData sensor_data;

// Timing
unsigned long last_sensor_report = 0;
constexpr unsigned long SENSOR_REPORT_MS = 100;  // Report every 100ms

char cmd_buffer[32];

void setup() {
    link.begin(SERIAL_BAUD);
    distance_init();
    flame_init();
    pump_init();
    motors_init();
}

void loop() {
    // Update all sensors (non-blocking)
    distance_update();
    flame_update();

    // Collect latest sensor readings
    sensor_data.distance_left = distance_get_left();
    sensor_data.distance_center = distance_get_center();
    sensor_data.distance_right = distance_get_right();
    sensor_data.flame_analog = flame_get_analog();
    sensor_data.flame_digital = flame_get_digital();

    // Send sensor data at regular intervals
    unsigned long now = millis();
    if (now - last_sensor_report >= SENSOR_REPORT_MS) {
        last_sensor_report = now;
        link.sendSensors(sensor_data);
    }

    // Check for incoming commands from Raspberry Pi
    if (link.receiveCommand(cmd_buffer, sizeof(cmd_buffer))) {
        command_execute(cmd_buffer);
    }
}
