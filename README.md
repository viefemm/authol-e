# ⚡ Authol-E

> **Hybrid IoT & Serverless Academic Telemetry Orchestrator for ETHOL PENS**  
> *A high-reliability, event-driven session monitor, multi-student state synchronizer, and multi-channel notification dispatcher.*

[![Architecture](https://img.shields.io/badge/Architecture-Hybrid%20IoT%20%2B%20Serverless-indigo?style=flat-square)]()
[![Hardware](https://img.shields.io/badge/Hardware-ESP32%20PlatformIO-blue?style=flat-square)]()
[![Cloud Worker](https://img.shields.io/badge/Cloud%20Worker-GitHub%20Actions%20Python-emerald?style=flat-square)]()
[![State Database](https://img.shields.io/badge/State%20Database-Firebase%20RTDB-amber?style=flat-square)]()
[![Notification Channels](https://img.shields.io/badge/Notifications-WhatsApp%20%7C%20Telegram-25D366?style=flat-square)]()

---

## 🧭 System Overview

**Authol-E** is an enterprise-grade academic automation and telemetry orchestration platform built on a **Hybrid Infrastructure (IoT Microcontroller + Realtime Cloud State + Serverless Event-Driven Runners)**. It seamlessly interfaces with the campus digital learning ecosystem (*Electronic Teaching Online Learning / ETHOL PENS*).

The system operates with near-zero latency (< 15 seconds detection window), automatically authenticates against university CAS SSO gateways, synchronizes active lecture session participation across multiple student accounts concurrently (*multi-tenant*), and dispatches real-time diagnostics directly to student communication channels (WhatsApp and Telegram).

---

## 🏗️ System Architecture

```text
[ETHOL Lecture Session Opened by Lecturer]
                    │
                    ▼
┌─────────────────────────────────────────────────────────┐
│           ESP32 HARDWARE SCOUT (Campus / Home IoT)      │
│  - Low-power continuous watcher (15s polling window)    │
│  - Hardware RTC-guarded state debounce lock             │
│  - Instant Session Open Detection -> GitHub API Dispatch│
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│        REALTIME TELEMETRY & STATE HUB (Firebase RTDB)   │
│  - Master PIN Security & Centralized Student Registry   │
│  - Live Epoch Heartbeat & Power/Network Watchdog        │
│  - Dynamic 2-Week Kloter / Lab Shift Course Overrides   │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│       SERVERLESS CLOUD WORKER (GitHub Actions Parallel) │
│  - Ephemeral Multi-Threaded Execution (< 3 seconds)     │
│  - Isolated Cookie Jars (Zero Cross-Account Leakage)    │
│  - Automated Session Verification & Check-in Pipeline   │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│          MULTI-CHANNEL NOTIFICATION GATEWAY             │
│  - WhatsApp Instant Delivery Engine (Fonnte API)        │
│  - Interactive Telegram Alert Bot                       │
│  - Zero Fail-Silent Logging & Incident Telemetry        │
└─────────────────────────────────────────────────────────┘
```

---

## ✨ Key Features

### 1. ⚡ 100% Event-Driven On-Demand Execution
- **No Inefficient Cron Jobs:** Unlike traditional 5-minute cron schedules that waste compute and risk server rate-limiting, Authol-E executes purely on-demand.
- **Sub-Second Cloud Triggering:** The moment the hardware scout detects an open session, GitHub Actions is triggered via Repository Dispatch within milliseconds.

### 2. 🛡️ Zero Fail-Silent Architecture
- Every phase of the authentication and submission lifecycle (MIS CAS CAS-Redirect, ETHOL SSO Token Validation, Session Key Availability, and Server Responses) is guarded.
- Any anomaly (e.g. invalid student password, expired SSO ticket, or server downtime) triggers an immediate emergency alert to the affected student so they can take manual action.

### 3. 🔌 Power & Network Outage Watchdog
- **Hardware Boot Telemetry:** Sends an instant WhatsApp alert to the administrator when the ESP32 powers on (*e.g. power restored*).
- **Offline Health Monitor:** Actively detects power outages or Wi-Fi disconnection exceeding 2 minutes, dispatching an automated alert to the admin.
- **Anti-Duplicate Debounce Lock:** Utilizes non-volatile `RTC_DATA_ATTR` memory on the ESP32 to prevent duplicate boot messages during warm resets or serial DTR pulses.

### 4. 🔬 Smart Course Routing & Manual Session Safety
- **2-Week Shift / Kloter Filter:** Identifies bi-weekly lab courses and suppresses automated submission, sending a reminder for manual attendance only when it matches the student's scheduled shift.
- **Manual Attendance Detection:** If a student already attended the lecture manually, the system detects the response and records it as an informational notice rather than an error.

### 5. 📱 Responsive Web Management Console
- Modern, PIN-protected web console built with **Tailwind CSS + Alpine.js**.
- Live hardware telemetry monitor with sub-70s epoch health indicators.
- **"Verify ETHOL"** tool for real-time profiling (fetching student official names & NRP numbers directly from CAS SSO).
- Interactive multi-channel testing buttons for WhatsApp and Telegram gateways.

---

## 📂 Repository Structure

```text
authol-e/
├── .github/
│   └── workflows/
│       └── presensi.yml          # On-Demand Serverless Workflow & Verifier
├── cloud-worker/
│   ├── app_actions.py            # Parallel Cloud Worker & Verification Engine
│   ├── app.py                    # Standalone Local Python Worker (Optional)
│   └── requirements.txt          # Python Runtime Dependencies
├── dashboard/
│   └── index.html                # Responsive Web Console (Mobile-Optimized)
├── firmware-esp32/               # IoT Scout Firmware (PlatformIO Project)
│   ├── platformio.ini
│   ├── src/
│   │   └── main.cpp
│   └── lib/
├── firmware-arduino/             # IoT Scout Firmware (Arduino IDE Sketch)
│   ├── README.md                 # Step-by-step Arduino IDE Setup Guide
│   └── authol_e_scout/
│       ├── authol_e_scout.ino    # Main Arduino IDE Sketch
│       └── ...                   # Modular Drivers & Services
├── firebase_schema.json          # Pre-configured Realtime Database Schema
└── README.md                     # System Documentation
```

---

## ⚙️ Quick Start & Configuration

### 1. Database Setup (Firebase Realtime Database)
1. Create a project in the [Firebase Console](https://console.firebase.google.com/) and enable **Realtime Database**.
2. Set security rules to allow read/write access.
3. Import the default database structure from `firebase_schema.json`.

### 2. GitHub Secrets Configuration
In your GitHub repository, navigate to **Settings** ➔ **Secrets and variables** ➔ **Actions**, then add the following secrets:

| Secret Name | Description |
|---|---|
| `FIREBASE_URL` | Your Firebase Realtime Database URL (`https://<project>-default-rtdb.firebaseio.com`) |
| `FONNTE_TOKEN` | API Token from your [Fonnte Dashboard](https://fonnte.com) |
| `ADMIN_WA` | Administrator WhatsApp number for hardware health alerts (`628...`) |
| `TELEGRAM_BOT_TOKEN` | (Optional) Telegram Bot token from [@BotFather](https://t.me/BotFather) |

*(Student accounts and configuration are fetched dynamically from Firebase at runtime).*

### 3. Flash ESP32 Hardware Scout

#### Option A: Using PlatformIO (VS Code)
1. Open `firmware-esp32/` in **VS Code** with the **PlatformIO IDE** extension.
2. Edit `firmware-esp32/src/main.cpp` and update the `Config` namespace with your Wi-Fi and API credentials.
3. Connect your ESP32 via USB and upload:
   ```bash
   pio run --target upload
   ```

#### Option B: Using Arduino IDE
1. Open `firmware-arduino/authol_e_scout/authol_e_scout.ino` in **Arduino IDE**.
2. Install **ArduinoJson (v6.21.x)** via Library Manager.
3. Update the `Config` namespace in the main tab.
4. Select board **ESP32 Dev Module** and upload! *(See `firmware-arduino/README.md` for details)*.

---

## 🔒 Security & Session Privacy

- **Session Isolation:** Each student account operates within an independent `requests.Session()` cookie jar, preventing cross-tenant data contamination.
- **Ephemeral Runners:** Cloud workers run in short-lived Ubuntu containers where all memory and session states are wiped immediately upon completion.
- **Masked Credentials:** Web management console obscures passwords and API tokens by default with interactive reveal toggles.

---

## 📜 Disclaimer & Ethical Notice

**Authol-E** was developed for educational and research purposes to demonstrate modern **IoT Hardware Telemetry**, **Serverless Event-Driven Orchestration**, and **Distributed Multi-Channel Alert Systems**. Users are responsible for adhering to institutional policies regarding automated digital interaction.
