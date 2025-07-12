#include "include.h"
#include "secrets.h"

const char* ssid = SECRET_SSID;
const char* password = SECRET_PASS;

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);

const char broker[] = "192.168.1.111";

void connectWifi() {
  Serial.begin(9600);
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.println("Connecting to WiFi..");
  }
  Serial.println("Connected to the WiFi network");

  delay(3000);
}

void connectMQTT() {
  mqttClient.setServer(broker, 1883);
  // mqttClient.setKeepAlive(1);

  while (!mqttClient.connected()) {
    Serial.println("Connecting to MQTT...");
    if (mqttClient.connect("the_block")) {
      Serial.println("connected");
    } else {
      Serial.print("failed with state ");
      Serial.println(mqttClient.state());
      delay(2000);
    }
  }
}

void callback(char* topic, byte* payload, unsigned int length){
  Serial.print("Message arrived [");
  Serial.print(topic);
  Serial.print("] ");
  
  for (unsigned int i = 0; i < length; i++) {
    Serial.print((char)payload[i]);
  }
  Serial.println();
}