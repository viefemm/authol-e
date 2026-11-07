#pragma once

#include <Arduino.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>

class FirebaseService {
public:
  explicit FirebaseService(const String &baseUrl);

  // Kirim status heartbeat ESP32 ke Firebase beserta epoch unix timestamp
  bool updateHeartbeat(bool online, const String &lastMatkul, const String &status);

  // Reset flag offline_alert_sent saat ESP32 kembali menyala
  bool resetOfflineAlert();

  // Periksa apakah ada manual trigger dari Web Dashboard
  bool checkAndClearManualTrigger();

  // Catat event/riwayat ke Firebase /history
  bool logHistory(const String &matkul, const String &status, const String &message);

private:
  String baseUrl_;
};
