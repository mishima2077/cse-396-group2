// ===== SensorTest.ino =====
// 3x HC-SR04 sonar + flame sensor (AO + DO) okuma testi.
// Serial Monitor: 115200 baud
// Her 500ms'de bir tüm sensör değerlerini basar.

// ---- Pin tanımları (Config.h ile eşleşmeli) ----------------------------------------
// Sonar LEFT
const uint8_t TRIG_L = A5;
const uint8_t ECHO_L = A4;
// Sonar CENTER
const uint8_t TRIG_C = 2;
const uint8_t ECHO_C = 4;
// Sonar RIGHT
const uint8_t TRIG_R = A1;
const uint8_t ECHO_R = A0;
// Flame sensor
const uint8_t FLAME_AO = A3;   // analog (0-1023, düşük = ateş)
const uint8_t FLAME_DO = A2;   // dijital (LOW = ateş var)

const uint16_t SONAR_MAX_CM = 340;
const unsigned long PRINT_MS = 500;

// ------------------------------------------------------------------------------------

void setup() {
    Serial.begin(115200);

    pinMode(TRIG_L, OUTPUT); pinMode(ECHO_L, INPUT);
    pinMode(TRIG_C, OUTPUT); pinMode(ECHO_C, INPUT);
    pinMode(TRIG_R, OUTPUT); pinMode(ECHO_R, INPUT);
    pinMode(FLAME_DO, INPUT);

    digitalWrite(TRIG_L, LOW);
    digitalWrite(TRIG_C, LOW);
    digitalWrite(TRIG_R, LOW);

    Serial.println(F("=== SensorTest basladı (115200 baud) ==="));
    Serial.println(F("Sonar[cm]  L   C   R  |  Flame AO  DO"));
    Serial.println(F("-------------------------------------------"));
}

void loop() {
    static unsigned long tLast = 0;
    if (millis() - tLast < PRINT_MS) return;
    tLast = millis();

    uint16_t L = readSonar(TRIG_L, ECHO_L);
    uint16_t C = readSonar(TRIG_C, ECHO_C);
    uint16_t R = readSonar(TRIG_R, ECHO_R);

    uint16_t flameRaw = analogRead(FLAME_AO);
    bool     flameDO  = digitalRead(FLAME_DO) == LOW;

    Serial.print(F("Sonar  L="));  Serial.print(L);
    Serial.print(F("cm  C="));     Serial.print(C);
    Serial.print(F("cm  R="));     Serial.print(R);
    Serial.print(F("cm  |  Flame AO="));  Serial.print(flameRaw);
    Serial.print(F("  DO="));
    Serial.println(flameDO ? F("ATЕS VAR") : F("temiz"));
}

// Blocking sonar ölçümü — sadece test için
uint16_t readSonar(uint8_t trig, uint8_t echo) {
    digitalWrite(trig, LOW);
    delayMicroseconds(4);
    digitalWrite(trig, HIGH);
    delayMicroseconds(10);
    digitalWrite(trig, LOW);

    unsigned long dur = pulseIn(echo, HIGH, 20000UL);  // max 20ms timeout
    if (dur == 0) return SONAR_MAX_CM;
    uint16_t cm = (uint16_t)(dur / 58UL);
    return cm > SONAR_MAX_CM ? SONAR_MAX_CM : cm;
}
