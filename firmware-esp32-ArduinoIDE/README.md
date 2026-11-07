# 🛠️ Arduino IDE Setup Guide for Authol-E ESP32 Firmware

Panduan lengkap untuk membuka, mengonfigurasi, dan melakukan *flashing* firmware ESP32 Scout menggunakan **Arduino IDE**.

---

## 1. Persiapan Software & Board Package

1. Unduh dan pasang [Arduino IDE 2.x](https://www.arduino.cc/en/software).
2. Buka **File ➔ Preferences** (atau `Ctrl + ,`).
3. Pada kolom **Additional boards manager URLs**, tambahkan URL package ESP32 resmi dari Espressif:
   ```text
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```
4. Buka **Tools ➔ Board ➔ Boards Manager...**, cari **`esp32`** oleh **Espressif Systems**, lalu klik **Install** (versi `2.0.x` atau `3.x`).

---

## 2. Instalasi Library yang Dibutuhkan

Buka **Tools ➔ Manage Libraries...** (atau `Ctrl + Shift + I`), lalu cari dan pasang:

- **`ArduinoJson`** by *Benoit Blanchon* (Pilih versi **`6.21.x`**).

*(Library `WiFi`, `HTTPClient`, `WiFiClientSecure`, dan `time.h` sudah terpasang otomatis bawaan core ESP32).*

---

## 3. Membuka Project di Arduino IDE

1. Buka folder `firmware-esp32-ArduinoIDE/authol_e_scout/`.
2. Klik dua kali pada file **`authol_e_scout.ino`**.
3. Arduino IDE akan otomatis membuka file utama beserta seluruh tab modul pendukung (`HttpTransport`, `MisAuthService`, `EtholSessionService`, `FirebaseService`, `GitHubDispatcher`, dll).

---

## 4. Konfigurasi Kredensial

Kredensial disimpan di file **`secrets.h`** (di-ignore git, tidak ikut ter-upload ke GitHub).

1. Salin `secrets.h.example` menjadi `secrets.h` di folder yang sama dengan `authol_e_scout.ino`.
2. Isi nilainya:

```cpp
namespace Secrets {
  constexpr const char *kWifiSsid    = "YOUR_WIFI_SSID";
  constexpr const char *kWifiPass    = "YOUR_WIFI_PASSWORD";
  constexpr const char *kScoutUser   = "your_email@student.pens.ac.id";
  constexpr const char *kScoutPass   = "YOUR_SSO_PASSWORD";
  constexpr const char *kAdminWa     = "628xxxxxxxxxx";
  constexpr const char *kFonnteToken = "YOUR_FONNTE_TOKEN";
  constexpr const char *kFirebaseUrl = "https://YOUR_PROJECT_ID-default-rtdb.firebaseio.com";
  constexpr const char *kGitHubRepo  = "USERNAME/REPOSITORY";
  constexpr const char *kGitHubToken = "YOUR_GITHUB_TOKEN";
}
```

---

## 5. Pengaturan Board & Upload

1. Hubungkan board ESP32 ke komputer melalui kabel data USB.
2. Di menu **Tools**, atur konfigurasi berikut:
   - **Board:** `ESP32 Dev Module` (atau sesuai tipe board Anda)
   - **Upload Speed:** `921600` (atau `115200`)
   - **CPU Frequency:** `240MHz (WiFi/BT)`
   - **Flash Frequency:** `80MHz`
   - **Port:** Pilih COM Port yang terdeteksi (misal: `COM3`, `COM4`, dll)
3. Klik tombol **Upload** (tanda panah ke kanan ➔).
4. Setelah selesai (*Done uploading*), buka **Tools ➔ Serial Monitor** dengan baud rate **`115200`** untuk melihat proses booting, koneksi WiFi, dan pengintaian sesi presensi.
