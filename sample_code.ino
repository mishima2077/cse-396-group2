// Two BTS7960 Motor Driver Rectangle Test
// Sequence:
// 1) Move forward for 10 seconds
// 2) Turn right for 3 seconds
// 3) Repeat 4 times to draw a rectangle
//
// Pin order for each driver:
// RPWM, LPWM, R_EN, L_EN
//
// LEFT DRIVER:
// L_RPWM -> Arduino D5
// L_LPWM -> Arduino D6
// L_R_EN -> Arduino D8
// L_L_EN -> Arduino D9
//
// RIGHT DRIVER:
// R_RPWM -> Arduino D10
// R_LPWM -> Arduino D11
// R_R_EN -> Arduino D12
// R_L_EN -> Arduino D13
//
// IMPORTANT:
// Connect Arduino GND to BTS7960/battery GND for reliable control signals.

const int L_RPWM = 5;
const int L_LPWM = 6;
const int L_REN  = 8;
const int L_LEN  = 9;

const int R_RPWM = 10;
const int R_LPWM = 11;
const int R_REN  = 12;
const int R_LEN  = 13;

const int DRIVE_SPEED = 255;   // 0-255
const int TURN_SPEED  = 255;   // 0-255

const unsigned long FORWARD_MS = 2000UL;  // 10 seconds forward
const unsigned long TURN_MS    = 1200UL;   // 3 seconds right turn 4800 tam tur
const unsigned long STOP_MS    = 2000UL;    // short pause between moves

void setup() {
  Serial.begin(9600);

  pinMode(L_RPWM, OUTPUT);
  pinMode(L_LPWM, OUTPUT);
  pinMode(L_REN, OUTPUT);
  pinMode(L_LEN, OUTPUT);

  pinMode(R_RPWM, OUTPUT);
  pinMode(R_LPWM, OUTPUT);
  pinMode(R_REN, OUTPUT);
  pinMode(R_LEN, OUTPUT);

  enableDrivers();
  stopAll();

  Serial.println("Rectangle test started.");
  Serial.println("Forward: 10 seconds, Right turn: 3 seconds, Repeat: 4 times");
  Serial.println("Left: RPWM=5, LPWM=6, R_EN=8, L_EN=9");
  Serial.println("Right: RPWM=10, LPWM=11, R_EN=12, L_EN=13");

  delay(1000);
}

void loop() {
  drawRectangle();

  Serial.println("Rectangle complete. Stopping.");
  stopAll();

  while (true) {
    delay(1000);
  }
}

void drawRectangle() {
  for (int side = 1; side <= 4; side++) {
    Serial.print("Step ");
    Serial.print(side);
    Serial.println(": moving forward for 10 seconds");

    forward(DRIVE_SPEED);
    delay(FORWARD_MS);

    stopAll();
    delay(STOP_MS);

    Serial.print("Step ");
    Serial.print(side);
    Serial.println(": turning right for 3 seconds");

    turnRight(TURN_SPEED);
    delay(TURN_MS);

    stopAll();
    delay(STOP_MS);
  }
}

void enableDrivers() {
  digitalWrite(L_REN, HIGH);
  digitalWrite(L_LEN, HIGH);

  digitalWrite(R_REN, HIGH);
  digitalWrite(R_LEN, HIGH);
}

void leftForward(int speedVal) {
  speedVal = constrain(speedVal, 0, 255);

  analogWrite(L_RPWM, speedVal);
  analogWrite(L_LPWM, 0);
}

void leftReverse(int speedVal) {
  speedVal = constrain(speedVal, 0, 255);

  analogWrite(L_RPWM, 0);
  analogWrite(L_LPWM, speedVal);
}

void rightForward(int speedVal) {
  speedVal = constrain(speedVal, 0, 255);

  analogWrite(R_RPWM, 0);
  analogWrite(R_LPWM, speedVal);
}

void rightReverse(int speedVal) {
  speedVal = constrain(speedVal, 0, 255);

  analogWrite(R_RPWM, speedVal);
  analogWrite(R_LPWM, 0);
}

void forward(int speedVal) {
  leftForward(speedVal);
  rightForward(speedVal);
}

void reverse(int speedVal) {
  leftReverse(speedVal);
  rightReverse(speedVal);
}

void turnRight(int speedVal) {
  // Right tank turn:
  // Left side backward, right side forward.
  leftReverse(speedVal);
  rightForward(speedVal);
}

void turnLeft(int speedVal) {
  // Left tank turn:
  // Left side forward, right side backward.
  leftForward(speedVal);
  rightReverse(speedVal);
}

void stopAll() {
  analogWrite(L_RPWM, 0);
  analogWrite(L_LPWM, 0);

  analogWrite(R_RPWM, 0);
  analogWrite(R_LPWM, 0);
}
