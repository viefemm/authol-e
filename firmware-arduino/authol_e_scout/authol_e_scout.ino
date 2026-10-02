// ============================================================================
// ETHOL SCOUT BOT - ESP32 HYBRID WORKER
// Memantau presensi ETHOL PENS setiap 15 detik (1 Akun Pengintai),
// mengirim heartbeat realtime ke Firebase, dan memicu GitHub Actions
// untuk melakukan presensi paralel multi-akun saat sesi dibuka.
// Dilengkapi notifikasi online/offline ke Admin saat listrik/WiFi nyala/mati.
// Anti-double notification dengan RTC Memory & hardware debounce lock.
// ============================================================================

#include <Arduino.h>
#include <WiFi.h>
#include <ArduinoJson.h>

#include "TimeDriver.h"
#include "HttpTransport.h"
#include "MisAuthService.h"
#include "EtholSessionService.h"
#include "FirebaseService.h"
#include "GitHubDispatcher.h"
#include "Logger.h"
#include "Schedule.h"
#include "TextUtil.h"

// ----------------------------------------------------------------------------
// KONFIGURASI WIFI & KREDENSIAL (Sesuaikan dengan kredensial Anda)
// ----------------------------------------------------------------------------
namespace Config {
  // WiFi
  const char *kWifiSsid = "NAMA_WIFI_ANDA";
  const char *kWifiPass = "PASSWORD_WIFI_ANDA";

  // Akun Pengintai (Master Scout) - Cukup 1 akun untuk memantau presensi kelas
  const char *kScoutUser = "email_anda@student.pens.ac.id";
  const char *kScoutPass = "PASSWORD_SSO_ANDA";

  // Admin WhatsApp & Fonnte Token
  const char *kAdminWa     = "628xxxxxxxxxx";          // No WA Admin (format 628...)
  const char *kFonnteToken = "TOKEN_API_FONNTE_ANDA";  // Token Fonnte WhatsApp Gateway

  // Firebase Realtime Database
  const char *kFirebaseUrl = "https://YOUR_PROJECT_ID-default-rtdb.firebaseio.com";

  // GitHub Actions API (Untuk trigger On-Demand Presensi Paralel)
  const char *kGitHubRepo  = "USERNAME_GITHUB/NAMA_REPOSITORY";
  const char *kGitHubToken = "ghp_YOUR_PERSONAL_ACCESS_TOKEN"; // Token GitHub (repo scope)

  // Jadwal & Interval Pengecekan
  const int           kStartHour           = 6;     // 06:00 WIB
  const int           kEndHour             = 21;    // 21:00 WIB
  const unsigned long kScoutIntervalMs     = 15000; // Cek ETHOL tiap 15 detik
  const unsigned long kHeartbeatIntervalMs = 30000; // Heartbeat Firebase tiap 30 detik
}

// ----------------------------------------------------------------------------
// GLOBAL INSTANCES & RTC STATE
// ----------------------------------------------------------------------------
HttpTransport       gTransport("SCOUT");
MisAuthService      gMisAuth(gTransport);
EtholSessionService gEtholSession(gTransport);
FirebaseService     gFirebase(Config::kFirebaseUrl);
GitHubDispatcher    gGitHub(Config::kGitHubRepo, Config::kGitHubToken);
TimeDriver          gTimeDriver;

// RTC Memory: Bertahan saat software reset / DTR serial monitor restart
RTC_DATA_ATTR static uint32_t sLastBootNotifyEpoch = 0;

// State tracking
unsigned long gLastScoutTime     = 0;
unsigned long gLastHeartbeatTime = 0;
String        gLastCheckedMatkul = "-";
String        gLastTriggeredId   = "";
bool          gIsLoggedIn        = false;

// ----------------------------------------------------------------------------
// NOTIFIKASI ADMIN VIA FONNTE (ANTI-DOUBLE DEBOUNCE)
// ----------------------------------------------------------------------------
bool sendAdminWa(const String &msg) {
  static unsigned long lastSendMillis = 0;
  unsigned long now = millis();
  if (lastSendMillis != 0 && (now - lastSendMillis < 3000)) {
    delay(3000 - (now - lastSendMillis));
  }
  lastSendMillis = millis();

  WiFiClientSecure client;
  client.setInsecure();
  client.setTimeout(10000);
  HTTPClient http;
  http.setReuse(false);
  http.setTimeout(10000);

  if (!http.begin(client, "https://api.fonnte.com/send")) {
    return false;
  }

  http.addHeader("Authorization", Config::kFonnteToken);
  http.addHeader("Content-Type", "application/json");

  StaticJsonDocument<512> doc;
  doc["target"] = Config::kAdminWa;
  doc["message"] = msg;

  String payload;
  serializeJson(doc, payload);

  int code = http.POST(payload);
  http.end();
  client.stop();
  return (code == 200);
}

// ----------------------------------------------------------------------------
// FUNGSI AUTH & LOGIN
// ----------------------------------------------------------------------------
bool ensureLoggedIn() {
  if (gIsLoggedIn && gEtholSession.validate()) {
    return true;
  }

  domain::Logger::log("SCOUT", "Sesi ETHOL kedaluwarsa atau belum login. Melakukan login...");
  gTransport.clearMisCookies();
  gTransport.clearEtholCookies();

  if (!gMisAuth.login(Config::kScoutUser, Config::kScoutPass)) {
    domain::Logger::log("SCOUT", "❌ Gagal login ke MIS CAS");
    gIsLoggedIn = false;
    return false;
  }

  if (!gEtholSession.sso()) {
    domain::Logger::log("SCOUT", "❌ Gagal SSO ke ETHOL");
    gIsLoggedIn = false;
    return false;
  }

  gIsLoggedIn = true;
  domain::Logger::log("SCOUT", "✅ Login MIS & SSO ETHOL Berhasil!");
  return true;
}

// ----------------------------------------------------------------------------
// FUNGSI SCOUT PRESENSI
// ----------------------------------------------------------------------------
void runScoutCheck() {
  if (!ensureLoggedIn()) {
    gFirebase.updateHeartbeat(true, gLastCheckedMatkul, "Login Failed");
    return;
  }

  // 1. Ambil Notifikasi Presensi dari ETHOL
  HttpResult rn = gTransport.get("NOTIF",
    "https://ethol.pens.ac.id/api/notifikasi/mahasiswa?filterNotif=PRESENSI",
    CookiePolicy::EtholJar);

  if (rn.code != 200 || !rn.body.length()) {
    domain::Logger::log("SCOUT", "Notif API HTTP " + String(rn.code));
    return;
  }

  StaticJsonDocument<2048> docNotif;
  DeserializationError err = deserializeJson(docNotif, rn.body);
  if (err || !docNotif.is<JsonArray>() || docNotif.as<JsonArray>().size() == 0) {
    domain::Logger::log("SCOUT", "Tidak ada notifikasi presensi aktif.");
    gFirebase.updateHeartbeat(true, "-", "Standby - Tidak ada presensi");
    return;
  }

  JsonObject firstNotif = docNotif[0];
  String ket = firstNotif["keterangan"].as<String>();
  String dataTerkait = firstNotif["dataTerkait"].as<String>();

  if (ket.indexOf("Dosen telah membuka presensi") < 0) {
    domain::Logger::log("SCOUT", "Belum ada presensi yang dibuka dosen.");
    gFirebase.updateHeartbeat(true, "-", "Standby - Presensi belum dibuka");
    return;
  }

  int sepIdx = dataTerkait.lastIndexOf('-');
  if (sepIdx < 0) return;

  String kuliah = dataTerkait.substring(0, sepIdx);
  String js     = dataTerkait.substring(sepIdx + 1);
  kuliah.trim(); js.trim();

  int idxMatkul = ket.indexOf("untuk matakuliah ");
  String matkul = (idxMatkul >= 0) ? ket.substring(idxMatkul + 17) : ket;
  matkul.trim();
  gLastCheckedMatkul = matkul;

  domain::Logger::log("SCOUT", "📢 Presensi Dosen Terbuka: " + matkul + " [Kuliah: " + kuliah + "]");

  // 2. Cek apakah sesi presensi benar-benar OPEN
  String urlAktif = "https://ethol.pens.ac.id/api/presensi/aktif-kuliah?kuliah=" + kuliah + "&jenis_schema=" + js;
  HttpResult ra = gTransport.get("AKTIF", urlAktif, CookiePolicy::EtholJar);

  if (ra.code != 200) {
    domain::Logger::log("SCOUT", "Gagal cek aktif-kuliah (HTTP " + String(ra.code) + ")");
    return;
  }

  DynamicJsonDocument docAktif(1024);
  deserializeJson(docAktif, ra.body);
  JsonObject aktifObj;
  if (docAktif.is<JsonArray>() && docAktif.size() > 0) {
    aktifObj = docAktif[0];
  } else {
    aktifObj = docAktif.as<JsonObject>();
  }

  int isOpen = aktifObj["open"] | 0;
  String key = aktifObj["key"].as<String>();

  if (isOpen != 1 || !key.length()) {
    domain::Logger::log("SCOUT", "Sesi presensi belum aktif (LOCKED). Menunggu...");
    gFirebase.updateHeartbeat(true, matkul, "LOCKED - Menunggu dosen buka sesi");
    return;
  }

  // 3. Status OPEN -> Debounce check
  if (gLastTriggeredId == kuliah) {
    domain::Logger::log("SCOUT", "Presensi " + matkul + " sudah diproses sebelumnya (Debounce).");
    gFirebase.updateHeartbeat(true, matkul, "Sudah Diproses Cloud");
    return;
  }

  // 4. Trigger GitHub Actions Cloud Worker!
  domain::Logger::log("SCOUT", "🔥 SESI PRESENSI AKTIF! Memicu eksekusi Cloud Worker...");
  gFirebase.updateHeartbeat(true, matkul, "TRIGGERING_CLOUD");
  gFirebase.logHistory(matkul, "TRIGGERED", "ESP32 mendeteksi sesi buka presensi. Menjalankan Cloud Worker.");

  bool dispatched = gGitHub.triggerPresensi(matkul, kuliah);
  if (dispatched) {
    gLastTriggeredId = kuliah;
    domain::Logger::log("SCOUT", "✅ Sukses mendelegasikan presensi ke GitHub Actions!");
  }
}

// ----------------------------------------------------------------------------
// SETUP & LOOP
// ----------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(1000);
  domain::Logger::log("BOOT", "=== ETHOL HYBRID SCOUT BOT V2.0 START ===");

  HttpTransport::initLock();
  gTransport.beginInsecure();

  // Hubungkan WiFi
  domain::Logger::log("WIFI", "Menghubungkan ke " + String(Config::kWifiSsid) + "...");
  WiFi.mode(WIFI_STA);
  WiFi.begin(Config::kWifiSsid, Config::kWifiPass);

  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 30) {
    delay(500);
    Serial.print(".");
    retries++;
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    domain::Logger::log("WIFI", "✅ WiFi Terhubung! IP: " + WiFi.localIP().toString());
  } else {
    domain::Logger::log("WIFI", "⚠️ WiFi gagal terhubung, akan dicoba ulang pada loop.");
  }

  // Sinkronisasi NTP Time
  gTimeDriver.beginSync();

  // Kirim Notifikasi Online ke Admin WhatsApp (dengan RTC Anti-Duplicate Guard)
  struct tm ti;
  char timeBuf[32] = "Baru saja";
  if (getLocalTime(&ti, 1000)) {
    snprintf(timeBuf, sizeof(timeBuf), "%02d-%02d-%04d %02d:%02d:%02d WIB",
             ti.tm_mday, ti.tm_mon + 1, ti.tm_year + 1900,
             ti.tm_hour, ti.tm_min, ti.tm_sec);
  }

  time_t nowEpoch = time(nullptr);
  // Hanya kirim notif jika belum pernah dikirim dalam 60 detik terakhir (Cegah double-send saat DTR/serial restart)
  if (sLastBootNotifyEpoch == 0 || (nowEpoch > sLastBootNotifyEpoch && (nowEpoch - sLastBootNotifyEpoch > 60))) {
    sLastBootNotifyEpoch = (uint32_t)nowEpoch;
    String bootMsg = "🟢 *ESP32 SCOUT BOT ONLINE (NYALA)*\n\n"
                     "Hardware ESP32 aktif & terhubung ke WiFi.\n"
                     "📡 *SSID:* " + String(Config::kWifiSsid) + "\n"
                     "🌐 *IP:* " + WiFi.localIP().toString() + "\n"
                     "⏰ *Waktu:* " + String(timeBuf) + "\n\n"
                     "_Sistem monitoring ETHOL mulai beroperasi._";

    sendAdminWa(bootMsg);
    domain::Logger::log("NOTIF", "✅ Notifikasi Online terkirim ke Admin WhatsApp");
  } else {
    domain::Logger::log("NOTIF", "Debounce: Notifikasi Online dilewati (baru saja dikirim).");
  }

  // Heartbeat awal ke Firebase
  gFirebase.updateHeartbeat(true, "-", "ESP32 Online & Siap");

  // Inisialisasi timer agar tidak double-fire di awal loop
  gLastHeartbeatTime = millis();
  gLastScoutTime     = millis();
}

void loop() {
  // Pastikan WiFi tetap aktif
  if (WiFi.status() != WL_CONNECTED) {
    domain::Logger::log("WIFI", "WiFi terputus, menyambung ulang...");
    WiFi.reconnect();
    delay(3000);
    return;
  }

  unsigned long now = millis();

  // 1. Cek Manual Trigger & Heartbeat Firebase (Tiap 30 detik)
  if (now - gLastHeartbeatTime >= Config::kHeartbeatIntervalMs) {
    gLastHeartbeatTime = now;
    gFirebase.updateHeartbeat(true, gLastCheckedMatkul, "Scouting ETHOL...");
  }

  // Cek apakah ada instruksi manual trigger dari Web Dashboard
  if (gFirebase.checkAndClearManualTrigger()) {
    domain::Logger::log("SCOUT", "⚡ Menerima Instruksi Manual Trigger dari Web Dashboard!");
    gGitHub.triggerPresensi("Manual Trigger", "0");
    gFirebase.logHistory("Manual Trigger", "TRIGGERED", "Dipicu manual dari Web Dashboard");
  }

  // 2. Cek Presensi ETHOL (Setiap 15 detik)
  if (now - gLastScoutTime >= Config::kScoutIntervalMs) {
    gLastScoutTime = now;

    // Cek jadwal perkuliahan (Senin-Jumat, 06:00 - 21:00 WIB)
    struct tm ti;
    bool inWindow = true;
    if (gTimeDriver.now(ti)) {
      inWindow = gTimeDriver.inWindow(ti, Config::kStartHour, Config::kEndHour);
    }

    if (inWindow) {
      runScoutCheck();
    } else {
      domain::Logger::log("SCOUT", "Di luar jam aktif sekolah (06:00 - 21:00 WIB). Standby.");
      gFirebase.updateHeartbeat(true, "-", "Standby - Di luar jam kuliah");
    }
  }

  delay(200);
}
