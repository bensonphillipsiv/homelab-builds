#pragma once
#include <Arduino.h>

#include <WiFi.h>
#include <PubSubClient.h>
// #include <MQTT.h>
#include <ArduinoJson.h>

// MPU
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_MPU6050.h>

// Wifi and MQTT
extern PubSubClient mqttClient;
void connectWifi();
void connectMQTT();
void callback(char* topic, byte* payload, unsigned int length);

extern Adafruit_MPU6050 mpu;
void configureMPU();
void pollMPU();