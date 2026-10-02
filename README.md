# ⚡ Authol-E (Automated Academic Telemetry & Session Orchestrator)

> **Hybrid IoT Scout & Serverless Cloud Orchestrator for ETHOL PENS**  
> *Sistem Pemantauan Sesi Akademik Cerdas, Sinkronisasi Status Multi-Akun Terdistribusi, dan Multi-Channel Notification Gateway.*

---

## 🧭 Ikhtisar Sistem

**Authol-E** adalah platform otomasi dan telemetri akademik berbasis arsitektur **Hybrid (Microcontroller IoT + Realtime Cloud State + Serverless Event-Driven Workers)** yang dirancang untuk mengintegrasikan ekosistem pembelajaran digital kampus (*Electronic Teaching Online Learning / ETHOL PENS*).

Sistem ini bekerja secara otomatis untuk mendeteksi pembukaan sesi perkuliahan secara *realtime* (< 15 detik), melakukan validasi tiket autentikasi SSO CAS PENS, menyinkronkan status partisipasi perkuliahan bagi banyak akun mahasiswa secara paralel (*multi-tenant*), serta mendistribusikan laporan aktivitas langsung ke kanal komunikasi personal (WhatsApp & Telegram).

---

## 🏗️ Arsitektur Sistem (Hybrid Infrastructure)

```text
[ETHOL Lecture Session Opened]
               │
               ▼
[ESP32 Hardware Scout (Kos/Home IoT)]
  - Low-power background watcher (15s polling window)
  - RTC-guarded hardware state tracking
  - Instant Event Detection -> Dispatch Webhook
               │
               ▼
[Realtime Telemetry & State Hub (Firebase RTDB)]
  - Master PIN Security Layer & Account Registry
  - Live Heartbeat Timestamp & Power/Network Watchdog
  - Dynamic Kloter & Shift Course Filter
               │
               ▼
[Serverless Cloud Worker (GitHub Actions On-Demand)]
  - Ephemeral Multi-Threaded Execution (< 3 detik)
  - Isolated CAS SSO Cookie Jars (Zero Token Leakage)
  - Automated Session Participation & Pre-check
               │
               ▼
[Multi-Channel Notification Gateway]
  - WhatsApp Delivery Engine (via Fonnte Gateway)
  - Telegram Interactive Notification Bot
  - Zero Fail-Silent Logging & Error Reporting
```

---

## ✨ Fitur-Fitur Utama

### 1. ⚡ 100% Event-Driven On-Demand Execution
- **Bukan Scheduled Cron:** Sistem tidak membuang kuota komputasi atau membanjiri server kampus dengan polling terjadwal setiap 5 menit.
- **Microsecond Triggering:** Begitu sensor IoT mendeteksi sesi kuliah dibuka oleh dosen, komputasi *serverless* langsung dipicu secara instan.

### 2. 🛡️ Zero Fail-Silent Architecture
- Setiap tahapan siklus verifikasi (Autentikasi MIS CAS, Validasi Token SSO ETHOL, Ketersediaan Kunci Sesi, hingga Respon Server) diawasi secara ketat.
- Jika terjadi anomali (misalnya password mahasiswa kedaluwarsa atau server kampus *down*), sistem langsung mengirimkan notifikasi darurat secara proaktif agar mahasiswa dapat segera mengambil tindakan manual.

### 3. 🔌 Power & Network Outage Watchdog
- **Hardware Boot Telemetry:** Mengirimkan notifikasi WhatsApp saat perangkat ESP32 baru saja menyala (*Power On* / Listrik kembali aktif).
- **Offline Health Monitor:** Mendeteksi jika perangkat keras kehilangan daya (mati lampu di kos) atau terputus dari WiFi selama > 2 menit dan secara otomatis mengirimkan peringatan ke administrator.
- **Anti-Duplicate Hardware Lock:** Menggunakan *RTC Memory Controller* untuk mencegah pengiriman pesan ganda saat terjadi *warm-reboot* atau koneksi serial.

### 4. 🔬 Smart Course Routing & Manual Session Safety
- **Kloter / Shift Filter:** Menyediakan filter khusus untuk mata kuliah laboratorium sistem 2 mingguan (kloter/shift) agar tidak melakukan sinkronisasi otomatis di luar giliran jadwal mahasiswa.
- **Duplicate Presence Detection:** Jika mahasiswa telah melakukan *check-in* secara manual di kelas, sistem mendeteksinya secara cerdas dan memberikan status informasi tanpa memicu pesan kesalahan.

### 5. 📱 Responsive Web Management Console
- Dashboard antarmuka web modern (*Tailwind CSS + Alpine.js*) terproteksi Master PIN.
- Pemantauan status kesehatan perangkat keras secara langsung (*Live Heartbeat Epoch < 70s*).
- Fitur **"Cek ETHOL"** untuk profiling instan (mengekstrak Nama Resmi & NRP mahasiswa langsung dari SSO CAS PENS).
- Tombol uji coba koneksi gateway WhatsApp dan Telegram secara interaktif.

---

## 📂 Struktur Repositori

```text
authol-e/
├── .github/
│   └── workflows/
│       └── presensi.yml          # GitHub Actions On-Demand Workflow & Verifier
├── cloud-worker/
│   ├── app_actions.py            # Parallel Cloud Worker & Verification Engine
│   ├── app.py                    # Standalone Local Python Worker (Optional)
│   └── requirements.txt          # Dependensi Python Runtime
├── dashboard/
│   └── index.html                # Web Management Console (Mobile-Optimized)
├── firmware-esp32/
│   ├── platformio.ini            # Konfigurasi PlatformIO & Dependencies
│   ├── src/
│   │   └── main.cpp              # IoT Scout Firmware (Hardware Event Detector)
│   └── lib/                      # Arsitektur Modular Drivers & Domain Services
├── firebase_schema.json          # Template Database Realtime Firebase
└── README.md                     # Dokumentasi Sistem
```

---

## ⚙️ Panduan Konfigurasi Singkat

### 1. Database State (Firebase Realtime Database)
1. Buat project baru di [Firebase Console](https://console.firebase.google.com/) dan aktifkan **Realtime Database**.
2. Impor struktur schema awal dari file `firebase_schema.json`.

### 2. GitHub Secrets Configuration
Pada repositori GitHub, masuk ke **Settings** ➔ **Secrets and variables** ➔ **Actions**, lalu daftarkan kredensial berikut:

| Nama Secret | Deskripsi |
|---|---|
| `FIREBASE_URL` | URL endpoint Firebase Realtime Database Anda |
| `FONNTE_TOKEN` | Token API gateway WhatsApp dari [Fonnte](https://fonnte.com) |
| `ADMIN_WA` | Nomor WhatsApp tujuan notifikasi telemetri / status perangkat |
| `TELEGRAM_BOT_TOKEN` | (Opsional) Token bot Telegram dari [@BotFather](https://t.me/BotFather) |

### 3. IoT Scout Firmware (ESP32)
1. Buka direktori `firmware-esp32/` menggunakan **PlatformIO IDE**.
2. Sesuaikan konfigurasi SSID WiFi, akun pemantau sesi, dan endpoint Firebase pada `src/main.cpp`.
3. Lakukan build dan flash ke modul ESP32 Anda:
   ```bash
   pio run --target upload
   ```

---

## 🔒 Privasi & Keamanan Sesi

- **Session Isolation:** Setiap akun dieksekusi dalam *cookie jar session* terisolasi secara mandiri pada memori runtime terpisah (*ephemeral container*).
- **Zero Local Plaintext Tokens:** Token sesi dan kredensial diproses secara terenkripsi saat transit (*TLS/HTTPS*) dan dimusnahkan segera setelah siklus eksekusi selesai.
- **Master PIN Gate:** Akses kontrol web console dilindungi oleh verifikasi PIN terenkripsi pada level database.

---

## 📜 Disclaimer & Ethical Notice

Proyek **Authol-E** dikembangkan murni sebagai bahan riset dan demonstrasi integrasi arsitektur **Internet of Things (IoT)**, orkestrasi komputasi *serverless event-driven*, serta implementasi sistem notifikasi telemetri terdistribusi. Segala penggunaan sistem diharapkan tetap mematuhi peraturan dan etika akademik yang berlaku di lingkungan institusi.
