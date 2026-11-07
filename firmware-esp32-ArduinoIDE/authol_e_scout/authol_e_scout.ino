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
#include "secrets.h"

// ----------------------------------------------------------------------------
// KONFIGURASI WIFI & KREDENSIAL (Sesuaikan dengan kredensial Anda)
// ----------------------------------------------------------------------------
namespace Config {
  const char *kWifiSsid = Secrets::kWifiSsid;
  const char *kWifiPass = Secrets::kWifiPass;

  // Akun Pengintai (Master Scout) - Cukup 1 akun untuk memantau presensi kelas
  const char *kScoutUser = Secrets::kScoutUser;
  const char *kScoutPass = Secrets::kScoutPass;

  const char *kAdminWa     = Secrets::kAdminWa;
  const char *kFonnteToken = Secrets::kFonnteToken;
  const char *kFirebaseUrl = Secrets::kFirebaseUrl;

  // GitHub Actions API (Untuk trigger On-Demand Presensi Paralel)
  const char *kGitHubRepo  = Secrets::kGitHubRepo;
  const char *kGitHubToken = Secrets::kGitHubToken;

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
unsigned long gWifiDownSince     = 0;
String        gLastCheckedMatkul = "-";
bool          gIsLoggedIn        = false;

// Loop progress counter untuk watchdog task (mendeteksi loop yang macet/hang)
volatile uint32_t gLoopTick = 0;

// Debounce multi-sesi: ingat beberapa kuliah yang sudah di-dispatch,
// supaya sesi lama yang masih OPEN tidak memblokir sesi matkul berikutnya.
const int kMaxTriggeredIds = 8;
String    gTriggeredIds[kMaxTriggeredIds];
int       gTriggeredCount = 0;
int       gTriggeredNext  = 0;

bool wasTriggered(const String &id) {
  for (int i = 0; i < gTriggeredCount; i++) {
    if (gTriggeredIds[i] == id) return true;
  }
  return false;
}

void rememberTriggered(const String &id) {
  if (wasTriggered(id)) return;
  gTriggeredIds[gTriggeredNext] = id;
  gTriggeredNext = (gTriggeredNext + 1) % kMaxTriggeredIds;
  if (gTriggeredCount < kMaxTriggeredIds) gTriggeredCount++;
}

// Watchdog: restart otomatis kalau loop utama tidak bergerak >5 menit
// (mis. TLS/HTTP macet total sehingga heartbeat berhenti).
void loopWatchdogTask(void *param) {
  uint32_t lastTick = gLoopTick;
  int stalled = 0;
  for (;;) {
    vTaskDelay(pdMS_TO_TICKS(60000));
    if (gLoopTick == lastTick) {
      stalled++;
      if (stalled >= 5) {
        domain::Logger::log("WDT", "Loop macet >5 menit. Restart ESP32 otomatis...");
        delay(100);
        ESP.restart();
      }
    } else {
      stalled = 0;
      lastTick = gLoopTick;
    }
  }
}

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

  DynamicJsonDocument docNotif(32768);
  DeserializationError err = deserializeJson(docNotif, rn.body);
  if (err || !docNotif.is<JsonArray>() || docNotif.as<JsonArray>().size() == 0) {
    domain::Logger::log("SCOUT", "Tidak ada notifikasi presensi aktif.");
    gFirebase.updateHeartbeat(true, "-", "Standby - Tidak ada presensi");
    return;
  }

  bool foundOpen = false;

  // Periksa hingga 5 notifikasi presensi terbaru
  for (size_t i = 0; i < docNotif.size() && i < 5; i++) {
    JsonObject notif = docNotif[i];
    String ket = notif["keterangan"] | "";
    String dataTerkait = notif["dataTerkait"] | "";

    if (ket.indexOf("Dosen telah membuka presensi") < 0) continue;

    int sepIdx = dataTerkait.lastIndexOf('-');
    if (sepIdx < 0) continue;

    String kuliah = dataTerkait.substring(0, sepIdx);
    String js     = dataTerkait.substring(sepIdx + 1);
    kuliah.trim(); js.trim();

    int idxMatkul = ket.indexOf("untuk matakuliah ");
    String matkul = (idxMatkul >= 0) ? ket.substring(idxMatkul + 17) : ket;
    matkul.trim();

    // 2. Cek apakah sesi presensi benar-benar OPEN
    String urlAktif = "https://ethol.pens.ac.id/api/presensi/aktif-kuliah?kuliah=" + kuliah + "&jenis_schema=" + js;
    HttpResult ra = gTransport.get("AKTIF", urlAktif, CookiePolicy::EtholJar);

    if (ra.code != 200) continue;

    DynamicJsonDocument docAktif(1024);
    deserializeJson(docAktif, ra.body);
    JsonObject aktifObj = (docAktif.is<JsonArray>() && docAktif.size() > 0) ? docAktif[0].as<JsonObject>() : docAktif.as<JsonObject>();

    int isOpen = aktifObj["open"] | 0;
    String key = aktifObj["key"] | "";

    if (isOpen != 1 || key.length() == 0) {
      continue;
    }

    foundOpen = true;
    gLastCheckedMatkul = matkul;

    // 3. Status OPEN -> Debounce check
    if (wasTriggered(kuliah)) {
      domain::Logger::log("SCOUT", "Presensi " + matkul + " sudah diproses sebelumnya (Debounce).");
      // Jangan break: lanjut cek notifikasi lain supaya sesi matkul berikutnya
      // yang sudah OPEN tetap bisa dipicu pada siklus yang sama.
      continue;
    }

    // 4. Trigger GitHub Actions Cloud Worker!
    domain::Logger::log("SCOUT", "🔥 SESI PRESENSI AKTIF: " + matkul + "! Memicu eksekusi Cloud Worker...");
    gFirebase.updateHeartbeat(true, matkul, "TRIGGERING_CLOUD");
    gFirebase.logHistory(matkul, "TRIGGERED", "ESP32 mendeteksi sesi buka presensi. Menjalankan Cloud Worker.");

    bool dispatched = gGitHub.triggerPresensi(matkul, kuliah);
    if (dispatched) {
      rememberTriggered(kuliah);
      domain::Logger::log("SCOUT", "✅ Sukses mendelegasikan presensi ke GitHub Actions!");
    }
    break;
  }

  if (!foundOpen) {
    domain::Logger::log("SCOUT", "Tidak ada sesi kuliah yang berstatus OPEN.");
    gFirebase.updateHeartbeat(true, gLastCheckedMatkul, "Scouting ETHOL - Standby");
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
  WiFi.setAutoReconnect(true);
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

  // Jalankan watchdog task di core 0 (loop Arduino ada di core 1)
  xTaskCreatePinnedToCore(loopWatchdogTask, "loop_wdt", 4096, NULL, 1, NULL, 0);
}

void loop() {
  gLoopTick++;

  // Pastikan WiFi tetap aktif
  if (WiFi.status() != WL_CONNECTED) {
    if (gWifiDownSince == 0) gWifiDownSince = millis();
    if (millis() - gWifiDownSince > 300000UL) {
      domain::Logger::log("WIFI", "WiFi terputus >5 menit. Restart ESP32 otomatis...");
      delay(100);
      ESP.restart();
    }
    domain::Logger::log("WIFI", "WiFi terputus, menyambung ulang...");
    WiFi.reconnect();
    delay(3000);
    return;
  }
  gWifiDownSince = 0;

  unsigned long now = millis();

  // 1. Cek Manual Trigger & Heartbeat Firebase (Tiap 30 detik)
  // CATATAN: pengecekan manual trigger HARUS di dalam blok interval ini.
  // Sebelumnya dipanggil setiap iterasi loop (~5x/detik) sehingga membuat
  // koneksi TLS terus-menerus, membanjiri Firebase, dan membuat ESP hang.
  if (now - gLastHeartbeatTime >= Config::kHeartbeatIntervalMs) {
    gLastHeartbeatTime = now;
    gFirebase.updateHeartbeat(true, gLastCheckedMatkul, "Scouting ETHOL...");

    // Cek apakah ada instruksi manual trigger dari Web Dashboard (fallback)
    if (gFirebase.checkAndClearManualTrigger()) {
      domain::Logger::log("SCOUT", "⚡ Menerima Instruksi Manual Trigger dari Web Dashboard!");
      gGitHub.triggerPresensi("Manual Trigger", "0");
      gFirebase.logHistory("Manual Trigger", "TRIGGERED", "Dipicu manual dari Web Dashboard");
    }
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
