#include <Arduino.h>
#include "include.h"


void setup() {
  connectWifi();
  connectMQTT();
  mqttClient.setCallback(callback);
  mqttClient.subscribe("block/menu");
  configureMPU();
}

void loop() {
  mqttClient.loop();
  pollMPU();
  delay(100);
}