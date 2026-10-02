"""
Script Pengujian Koneksi Fonnte (Manual Trigger)
Memeriksa status device Fonnte dan mengirim pesan uji coba WhatsApp.
"""

import os
import json
import requests
from datetime import datetime
import pytz

WIB = pytz.timezone("Asia/Jakarta")
now_str = datetime.now(WIB).strftime("%d-%m-%Y pukul %H:%M:%S WIB")

FONNTE_TOKEN = os.environ.get("FONNTE_TOKEN", "")
ACCOUNTS_JSON = os.environ.get("ACCOUNTS_JSON", "[]")


def check_device():
    print("=" * 50)
    print("1. MEMERIKSA STATUS DEVICE FONNTE...")
    print("=" * 50)
    if not FONNTE_TOKEN:
        print("❌ ERROR: FONNTE_TOKEN belum diatur di Secrets!")
        return False

    try:
        r = requests.post(
            "https://api.fonnte.com/device",
            headers={"Authorization": FONNTE_TOKEN},
            timeout=15
        )
        print(f"HTTP Status: {r.status_code}")
        data = r.json()
        print(f"Response: {json.dumps(data, indent=2)}")

        device_status = data.get("device_status", "unknown")
        name = data.get("name", "-")
        device = data.get("device", "-")

        print(f"Nama Device  : {name}")
        print(f"Nomor Device : {device}")
        print(f"Status WA    : {device_status}")

        if device_status == "connect":
            print("✅ Device Fonnte TERHUBUNG ke WhatsApp!")
            return True
        else:
            print("⚠️ Device Fonnte TIDAK TERHUBUNG (Periksa pairing QR di dashboard Fonnte)")
            return False
    except Exception as e:
        print(f"❌ Gagal cek device: {e}")
        return False


def send_test_message(target: str, name: str):
    print("\n" + "=" * 50)
    print(f"2. TEST KIRIM WA KE: {name} ({target})")
    print("=" * 50)
    if not target:
        print(f"⚠️ Target nomor WA kosong untuk '{name}', dilewati.")
        return

    msg = (
        f"🔔 *TEST KONEKSI FONNTE - ETHOL BOT*\n\n"
        f"👤 *Akun:* {name}\n"
        f"📱 *Target:* {target}\n"
        f"⏰ *Waktu:* {now_str}\n"
        f"📡 *Status:* Cloud GitHub Actions ➔ Fonnte API ➔ WhatsApp OK!\n\n"
        f"_Ini adalah pesan uji coba manual._"
    )

    try:
        r = requests.post(
            "https://api.fonnte.com/send",
            headers={"Authorization": FONNTE_TOKEN},
            json={"target": target, "message": msg},
            timeout=15
        )
        print(f"HTTP Status: {r.status_code}")
        data = r.json()
        print(f"Response: {json.dumps(data, indent=2)}")
        if data.get("status") is True:
            print(f"✅ Berhasil mengirim pesan WA ke {target}!")
        else:
            print(f"❌ Gagal mengirim WA: {data.get('reason', 'Unknown reason')}")
    except Exception as e:
        print(f"❌ Exception kirim WA: {e}")


def main():
    print(f"==================================================")
    print(f"  ETHOL BOT - FONNTE CONNECTION CHECK")
    print(f"  Waktu: {now_str}")
    print(f"==================================================\n")

    check_device()

    try:
        accounts = json.loads(ACCOUNTS_JSON)
    except Exception as e:
        print(f"❌ Error parse ACCOUNTS_JSON: {e}")
        accounts = []

    if not accounts:
        print("\n⚠️ ACCOUNTS_JSON kosong!")
        return

    print(f"\nDitemukan {len(accounts)} akun terdaftar untuk pengujian.")
    for acc in accounts:
        user = acc.get("user", "Unknown")
        target = acc.get("wa_target", "")
        send_test_message(target, user.split("@")[0])

    print("\n==================================================")
    print("  PENGUJIAN SELESAI")
    print("==================================================")


if __name__ == "__main__":
    main()
