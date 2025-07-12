#include "include.h"

Adafruit_MPU6050 mpu;

void configureMPU() {
  while (!mpu.begin(0x68, &Wire1)) {
    Serial.println("Failed to find MPU6050 chip");
    delay(1000);
  }
  Serial.println("MPU6050 Found!");

  mpu.setAccelerometerRange(MPU6050_RANGE_2_G);
  mpu.setGyroRange(MPU6050_RANGE_500_DEG);
  mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
}

void pollMPU() {
  sensors_event_t a, g, temp;
  mpu.getEvent(&a, &g, &temp);

  float mx = 0.10250590963473276 * 0.9996916345088431;
  float bx = -0.05830565531616768 + 0.004024126774224875;
  float my = 0.10207676841626437 * 0.9997803159233332;
  float by = -0.005002860392721587 + 0.0017838308498001696;
  float mz = 0.09882532884884036 * 0.999992642405489;
  float bz = 0.21923720428834315 + 0.0013995298465419989;

  float cal_accx = mx * a.acceleration.x + bx;
  float cal_accy = my * a.acceleration.y + by;
  float cal_accz = mz * a.acceleration.z + bz;

  /* Print out the values */
  Serial.print("Calibrated Acceleration X: ");
  Serial.print(cal_accx);
  Serial.print(", Y: ");
  Serial.print(cal_accy);
  Serial.print(", Z: ");
  Serial.print(cal_accz);
  Serial.println(" m/s^2");

  Serial.print("Rotation X: ");
  Serial.print(g.gyro.x);
  Serial.print(", Y: ");
  Serial.print(g.gyro.y);
  Serial.print(", Z: ");
  Serial.print(g.gyro.z);
  Serial.println(" rad/s");

  StaticJsonDocument<96> data_doc;

  data_doc["accx"] = cal_accx;
  data_doc["accy"] = cal_accy;
  data_doc["accz"] = cal_accz;

  data_doc["gyrx"] = g.gyro.x;
  data_doc["gyry"] = g.gyro.y;
  data_doc["gyrz"] = g.gyro.z;

  char data[256];
  size_t n = serializeJson(data_doc, data);

  bool success = mqttClient.publish("block/data", data, n);
  if (success) {
    Serial.println("Publish successful!");
  } else {
    Serial.println("Publish failed!");
  }
}