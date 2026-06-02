// ===== PumpTest.ino =====
// R385 su pompası açma/kapama testi.
// Serial Monitor: 115200 baud
// 3 saniye aç → 3 saniye kapat → tekrar

const uint8_t PIN_PUMP = 7;   // Config.h PIN_WATER_PUMP

const unsigned long ON_MS  = 3000UL;
const unsigned long OFF_MS = 3000UL;

void setup() {
    Serial.begin(115200);
    pinMode(PIN_PUMP, OUTPUT);
    digitalWrite(PIN_PUMP, LOW);
    Serial.println(F("=== PumpTest basladı ==="));
    Serial.println(F("3sn AC -> 3sn KAPAT -> tekrar"));
}

void loop() {
    digitalWrite(PIN_PUMP, HIGH);
    Serial.println(F("PUMP: ACIK"));
    delay(ON_MS);

    digitalWrite(PIN_PUMP, LOW);
    Serial.println(F("PUMP: KAPALI"));
    delay(OFF_MS);
}
