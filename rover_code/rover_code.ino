#include "water_pump.h"

/*
#include "distance.h"
#include "flame.h"

void setup() {
    Serial.begin(9600);
    distance_init();
    flame_init();
}

void loop() {
    uint16_t flame_analog[FLAME_SENSOR_COUNT];
    bool     flame_digital[FLAME_SENSOR_COUNT];

    uint16_t dist = distance_read_cm();
    flame_read(flame_analog);
    flame_detected(flame_digital);

    Serial.println("--------------------");

    Serial.print("Distance : ");
    Serial.print(dist);
    Serial.println(" cm");

    Serial.println("Flame sensors:");
    for (uint8_t i = 0; i < FLAME_SENSOR_COUNT; i++) {
        Serial.print("  [");
        Serial.print(i);
        Serial.print("] analog=");
        Serial.print(flame_analog[i]);
        Serial.print("  detected=");
        Serial.println(flame_digital[i] ? "YES" : "no");
    }

    delay(500);
}
*/

void setup() {
    Serial.begin(9600);
    pump_init();
}

void loop() {
    pump_start();
    Serial.println("Pump ON");
    delay(2000);

    pump_stop();
    Serial.println("Pump OFF");
    delay(2000);
}
