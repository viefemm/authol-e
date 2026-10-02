#include "FirebaseService.h"
#include <ArduinoJson.h>
#include <Logger.h>
#include <time.h>

static String getFormattedTime() {
  struct tm ti;
  if (getLocalTime(&ti, 500)) {
    char buf[32];
    snprintf(buf, sizeof(buf), "%04d-%02d-%02d %02d:%02d:%02d WIB",
             ti.tm_year + 1900, ti.tm_mon + 1, ti.tm_mday,
             ti.tm_hour, ti.tm_min, ti.tm_sec);
    return String(buf);
  }
  return String(millis() / 1000) + "s uptime";
}

FirebaseService::FirebaseService(const String &baseUrl) : baseUrl_(baseUrl) {
  if (baseUrl_.endsWith("/")) {
    baseUrl_.remove(baseUrl_.length() - 1);
  }
}

bool FirebaseService::updateHeartbeat(bool online, const String &lastMatkul, const String &status) {
  WiFiClientSecure client;
  client.setInsecure();
  HTTPClient http;

  String url = baseUrl_ + "/device_status.json";
  if (!http.begin(client, url)) {
    return false;
  }

  http.addHeader("Content-Type", "application/json");

  time_t nowEpoch = time(nullptr);

  StaticJsonDocument<384> doc;
  doc["esp32_online"] = online;
  doc["last_seen"] = getFormattedTime();
  doc["last_seen_epoch"] = (unsigned long)nowEpoch;
  doc["last_checked_matkul"] = lastMatkul;
  doc["last_status"] = status;
  doc["offline_alert_sent"] = false; // Reset alert karena ESP32 aktif

  String payload;
  serializeJson(doc, payload);

  int code = http.PATCH(payload);
  http.end();
  return (code == 200);
}

bool FirebaseService::resetOfflineAlert() {
  WiFiClientSecure client;
  client.setInsecure();
  HTTPClient http;

  String url = baseUrl_ + "/device_status/offline_alert_sent.json";
  if (!http.begin(client, url)) {
    return false;
  }

  http.addHeader("Content-Type", "application/json");
  int code = http.PUT("false");
  http.end();
  return (code == 200);
}

bool FirebaseService::checkAndClearManualTrigger() {
  WiFiClientSecure client;
  client.setInsecure();
  HTTPClient http;

  String url = baseUrl_ + "/device_status/manual_trigger.json";
  if (!http.begin(client, url)) {
    return false;
  }

  int code = http.GET();
  if (code != 200) {
    http.end();
    return false;
  }

  String body = http.getString();
  http.end();

  body.trim();
  if (body == "true") {
    // Reset trigger to false
    HTTPClient httpReset;
    WiFiClientSecure clientReset;
    clientReset.setInsecure();
    httpReset.begin(clientReset, url);
    httpReset.addHeader("Content-Type", "application/json");
    httpReset.PUT("false");
    httpReset.end();
    return true;
  }
  return false;
}

bool FirebaseService::logHistory(const String &matkul, const String &status, const String &message) {
  WiFiClientSecure client;
  client.setInsecure();
  HTTPClient http;

  String url = baseUrl_ + "/history.json";
  if (!http.begin(client, url)) {
    return false;
  }

  http.addHeader("Content-Type", "application/json");

  StaticJsonDocument<256> doc;
  doc["timestamp"] = getFormattedTime();
  doc["matkul"] = matkul;
  doc["status"] = status;
  doc["message"] = message;

  String payload;
  serializeJson(doc, payload);

  int code = http.POST(payload);
  http.end();
  return (code == 200);
}
