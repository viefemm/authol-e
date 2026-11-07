#include "GitHubDispatcher.h"
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>
#include <Logger.h>

GitHubDispatcher::GitHubDispatcher(const String &repo, const String &token)
    : repo_(repo), token_(token) {}

bool GitHubDispatcher::triggerPresensi(const String &matkul, const String &kuliahId) {
  WiFiClientSecure client;
  client.setInsecure();
  HTTPClient http;

  String url = "https://api.github.com/repos/" + repo_ + "/dispatches";
  if (!http.begin(client, url)) {
    domain::Logger::log("GITHUB", "Gagal inisialisasi koneksi ke GitHub API");
    return false;
  }

  http.addHeader("Authorization", "Bearer " + token_);
  http.addHeader("Accept", "application/vnd.github+json");
  http.addHeader("User-Agent", "ESP32-Ethol-Scout/2.0");
  http.addHeader("Content-Type", "application/json");

  StaticJsonDocument<256> doc;
  doc["event_type"] = "ethol_presensi_trigger";
  JsonObject payload = doc.createNestedObject("client_payload");
  payload["matkul"] = matkul;
  payload["kuliah_id"] = kuliahId;

  String body;
  serializeJson(doc, body);

  domain::Logger::log("GITHUB", "Mengirim repository_dispatch ke GitHub Actions...");
  int code = http.POST(body);
  String resp = http.getString();
  http.end();

  bool ok = (code == 204 || code == 200 || code == 201);
  if (ok) {
    domain::Logger::log("GITHUB", "✅ Berhasil memicu Cloud Worker di GitHub Actions! (HTTP " + String(code) + ")");
  } else {
    domain::Logger::log("GITHUB", "❌ Gagal memicu GitHub Actions: HTTP " + String(code) + " " + resp);
  }
  return ok;
}
