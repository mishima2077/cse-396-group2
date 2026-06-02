/****************************************************************************************
 *  FIRE-FIGHTING FREE ROAM ROBOT  —  Arduino Uno  +  Raspberry Pi (serial)
 *
 *  Pi sürekli görüntü işler, ateş görünce "FIRE,<x>\n" yollar (x: 0..639, 1 sn'de bir).
 *  Arduino normalde free-roam koşturur; FIRE gelince misyona geçer:
 *    FIRE_AIM (ortala) -> FIRE_APPROACH (yaklaş, FIRE_STOP_CM'de dur) ->
 *    FIRE_SPRAY (pompa aç, flame 3 sn temizse) -> FIRE_DONE -> free-roam.
 *  Failsafe: misyon 8 sn'de biter (abort), Pi verisi 3 sn kesilirse abort.
 *
 *  delay() YOK — tüm zamanlama millis()/micros().
 *  Pinler: pompa D3, flame AO A2. D0/D1 -> Pi serial (boş bırakıldı).
 ****************************************************************************************/

#include "Config.h"
#include "SkidSteerMotors.h"
#include "TripleSonarArray.h"
#include "WaterPump.h"
#include "FlameSensor.h"
#include "SerialLink.h"
#include "SlaveController.h"

SkidSteerMotors  motors;
TripleSonarArray sonar;
WaterPump        pump;
FlameSensor      flame;
SerialLink       link;
SlaveController  controller;
PiCommand        cmd;     // Pi'den gelen güncel komut

void setup() {
  link.begin();                        // Serial.begin dahil
  motors.begin();
  sonar.begin();
  pump.begin();
  flame.begin();
  controller.begin(&motors, &pump);    // sonar/flame Pi'ye raporlanır, Arduino karar vermez
}

void loop() {
  link.update(cmd);                                               // Pi komutlarını parse et
  sonar.update();                                                 // sonar round-robin
  controller.update(cmd);                                         // komutu uygula, timeout kontrol
  link.reportSensors(sonar.left(), sonar.center(), sonar.right(), flame.raw()); // Pi'ye veri gönder
}
