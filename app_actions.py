"""
ETHOL Presensi Bot - Cloud Parallel Worker & Account Verifier
Mengambil daftar akun aktif langsung dari Firebase Realtime Database,
menjalankan presensi secara paralel, memverifikasi akun ETHOL / MIS CAS,
mencatat log ke Firebase, mengirimkan notifikasi multi-channel (WhatsApp via Fonnte & Telegram),
dan memantau kesehatan ESP32 (Cloud Watchdog).
Dilengkapi perlindungan:
- Zero Fail-Silent di setiap titik kegagalan
- Deteksi presensi manual (jika sudah absen duluan)
- Filter khusus matakuliah sistem kloter 2 mingguan (221835, 221847, 221839, 221840)
"""

import os
import time
import json
import logging
import threading
import requests
from datetime import datetime
import pytz
import re
from urllib.parse import urlparse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

WIB = pytz.timezone("Asia/Jakarta")

FIREBASE_URL       = os.environ.get("FIREBASE_URL", "https://ethol-bot-default-rtdb.firebaseio.com")
FONNTE_TOKEN       = os.environ.get("FONNTE_TOKEN", "wB7GEFCDTyDLpU2PjNPp")
ADMIN_WA           = os.environ.get("ADMIN_WA", "6285175062616")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
JAM_MULAI          = int(os.environ.get("JAM_MULAI", "6"))
JAM_SELESAI        = int(os.environ.get("JAM_SELESAI", "21"))

# Matakuliah khusus 2 minggu sekali (Sistem Kloter) yang memerlukan presensi manual
DEFAULT_MANUAL_KULIAH_IDS = ["221835", "221847", "221839", "221840"]


def now_wib() -> datetime:
    return datetime.now(WIB)

def in_window() -> bool:
    n = now_wib()
    return n.weekday() < 5 and JAM_MULAI <= n.hour < JAM_SELESAI

def timestamp_str() -> str:
    return now_wib().strftime("%d-%m-%Y pukul %H:%M WIB")

def date_stamp() -> str:
    return now_wib().strftime("%Y%m%d")

def log_to_firebase(matkul: str, status: str, message: str):
    """Mencatat aktivitas presensi ke Firebase Realtime Database."""
    try:
        payload = {
            "timestamp": now_wib().strftime("%Y-%m-%d %H:%M:%S"),
            "matkul": matkul,
            "status": status,
            "message": message
        }
        requests.post(f"{FIREBASE_URL}/history.json", json=payload, timeout=10)
    except Exception as e:
        logging.getLogger("FIREBASE").error(f"Gagal simpan log ke Firebase: {e}")

def get_tg_token() -> str:
    global TELEGRAM_BOT_TOKEN
    if TELEGRAM_BOT_TOKEN:
        return TELEGRAM_BOT_TOKEN
    try:
        r = requests.get(f"{FIREBASE_URL}/config/telegram_bot_token.json", timeout=5)
        if r.status_code == 200 and r.json():
            TELEGRAM_BOT_TOKEN = str(r.json())
            return TELEGRAM_BOT_TOKEN
    except Exception:
        pass
    return ""

def get_manual_kuliah_ids() -> list:
    """Mengambil daftar ID matakuliah sistem kloter 2 mingguan."""
    try:
        r = requests.get(f"{FIREBASE_URL}/config/manual_kuliah_ids.json", timeout=5)
        if r.status_code == 200 and r.json():
            data = r.json()
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
            elif isinstance(data, str):
                return [x.strip() for x in data.split(",") if x.strip()]
    except Exception:
        pass
    return DEFAULT_MANUAL_KULIAH_IDS

def is_already_present_msg(msg_str: str) -> bool:
    """Mendeteksi apakah respons server menandakan mahasiswa sudah presensi manual."""
    if not msg_str:
        return False
    lower = msg_str.lower()
    return ("sudah" in lower and any(w in lower for w in ["presensi", "absen", "isi", "mengisi", "ada", "tercatat", "terdaftar"])) or ("already" in lower)

def get_fonnte_token() -> str:
    global FONNTE_TOKEN
    if FONNTE_TOKEN:
        return FONNTE_TOKEN
    try:
        r = requests.get(f"{FIREBASE_URL}/config/fonnte_token.json", timeout=5)
        if r.status_code == 200 and r.json():
            FONNTE_TOKEN = str(r.json())
            return FONNTE_TOKEN
    except Exception:
        pass
    return FONNTE_TOKEN or os.environ.get("FONNTE_TOKEN", "wB7GEFCDTyDLpU2PjNPp")

def send_wa(target: str, message: str) -> bool:
    token = get_fonnte_token()
    if not token or not target:
        return False
    try:
        r = requests.post(
            "https://api.fonnte.com/send",
            headers={"Authorization": token},
            json={"target": target, "message": message},
            timeout=15
        )
        ok = r.status_code == 200 and r.json().get("status") is True
        logging.getLogger("FONNTE").info(f"{'OK' if ok else 'GAGAL'} WA ke {target}: HTTP {r.status_code}")
        return ok
    except Exception as e:
        logging.getLogger("FONNTE").error(f"Gagal kirim WA ke {target}: {e}")
        return False

def send_telegram(chat_id: str, message: str) -> bool:
    token = get_tg_token()
    if not token or not chat_id:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
            timeout=15
        )
        ok = r.status_code == 200 and r.json().get("ok") is True
        logging.getLogger("TELEGRAM").info(f"{'OK' if ok else 'GAGAL'} Telegram ke {chat_id}: HTTP {r.status_code}")
        return ok
    except Exception as e:
        logging.getLogger("TELEGRAM").error(f"Gagal kirim Telegram ke {chat_id}: {e}")
        return False

def notify_client(acc: dict, message_wa: str, message_tg: str = ""):
    """Mengirim notifikasi ke semua kanal client yang aktif (WhatsApp & Telegram)."""
    wa = acc.get("wa_target", "")
    tg = acc.get("tg_chat_id", "")
    msg_tg = message_tg or message_wa

    if wa:
        send_wa(wa, message_wa)
    if tg:
        send_telegram(tg, msg_tg)


def check_esp32_offline_watchdog():
    """Memeriksa apakah ESP32 offline (mati lampu / WiFi putus) dan memberi tahu Admin."""
    try:
        r = requests.get(f"{FIREBASE_URL}/device_status.json", timeout=10)
        if r.status_code != 200:
            return
        dev = r.json() or {}
        last_epoch = dev.get("last_seen_epoch", 0)
        alert_sent = dev.get("offline_alert_sent", False)
        now_epoch = int(time.time())

        # Fallback jika epoch belum tersimpan tapi string ada
        if not last_epoch and dev.get("last_seen"):
            try:
                raw = dev["last_seen"].replace(" WIB", "").strip()
                dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
                dt = WIB.localize(dt)
                last_epoch = int(dt.timestamp())
            except Exception:
                pass

        # Jika > 120 detik tidak ada heartbeat dan belum ada notif offline dikirim
        if last_epoch and (now_epoch - last_epoch > 120) and not alert_sent:
            logging.warning("⚠️ ESP32 terdeteksi OFFLINE! Mengirim notifikasi darurat ke Admin...")
            msg = (
                f"🔴 *PERINGATAN: ESP32 OFFLINE (MATI LAMPU / TERPUTUS)*\n\n"
                f"Hardware ESP32 tidak mengirim heartbeat selama >2 menit.\n"
                f"Kemungkinan terjadi *mati lampu di kos* atau *WiFi terputus*.\n\n"
                f"⏰ *Terakhir Aktif:* {dev.get('last_seen', '-')}\n"
                f"📌 *Status Terakhir:* {dev.get('last_status', '-')}\n"
                f"📚 *Matkul Terakhir:* {dev.get('last_checked_matkul', '-')}\n\n"
                f"_Notifikasi otomatis dari Cloud Watchdog._"
            )
            send_wa(ADMIN_WA, msg)
            requests.put(f"{FIREBASE_URL}/device_status/offline_alert_sent.json", json=True, timeout=10)
            log_to_firebase("ESP32 Watchdog", "OFFLINE_ALERT", "Notifikasi ESP32 mati dikirim ke Admin WhatsApp")
    except Exception as e:
        logging.error(f"Error checking ESP32 health watchdog: {e}")


def get_active_accounts():
    """Mengambil daftar akun aktif dari Firebase."""
    try:
        r = requests.get(f"{FIREBASE_URL}/accounts.json", timeout=10)
        if r.status_code == 200:
            data = r.json()
            raw_list = data if isinstance(data, list) else (list(data.values()) if isinstance(data, dict) else [])
            active_list = [acc for acc in raw_list if acc.get("is_active") is True]
            if active_list:
                logging.info(f"Berhasil fetch {len(active_list)} akun aktif dari Firebase.")
                return active_list
    except Exception as e:
        logging.error(f"Gagal fetch akun dari Firebase: {e}")

    fallback_json = os.environ.get("ACCOUNTS_JSON", "[]")
    try:
        raw = json.loads(fallback_json)
        return [a for a in raw if a.get("is_active", True)]
    except Exception:
        return []


class AccountWorker:
    def __init__(self, config: dict):
        self.config         = config
        self.user           = config["user"]
        self.password       = config["pass"]
        self.wa_target      = config.get("wa_target", "")
        self.tg_chat_id     = config.get("tg_chat_id", "")
        self.name           = config.get("name", self.user.split("@")[0])
        self.label          = self.name
        self.log            = logging.getLogger(self.label)
        self.session        = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0 (EtholBot/2.0)"})
        self.student_number = ""
        self.student_name   = ""
        self.student_email  = ""

    def _mis_login(self) -> bool:
        self.log.info("Login MIS CAS...")
        try:
            cas_url = "https://online.mis.pens.ac.id/index.php?Login=1&halAwal=1"
            body = ""
            for _ in range(6):
                r = self.session.get(cas_url, allow_redirects=False, timeout=15)
                if r.status_code in (301, 302, 303, 307):
                    loc = r.headers.get("Location", cas_url)
                    if loc.startswith("/"):
                        loc = "https://login.pens.ac.id" + loc
                    cas_url = loc
                    continue
                if r.status_code == 200:
                    body = r.text
                break

            if not body:
                self.log.error("Login gagal: body kosong")
                return False

            lt_match     = re.search(r'name="lt"\s+value="([^"]+)"', body)
            action_match = re.search(r'action="([^"]+)"', body)
            if not lt_match or not action_match:
                self.log.error("Login gagal: lt/action tidak ditemukan")
                return False

            lt     = lt_match.group(1)
            action = action_match.group(1)
            if action.startswith("/"):
                parsed = urlparse(cas_url)
                action = f"{parsed.scheme}://{parsed.netloc}{action}"

            payload = {
                "username": self.user, "password": self.password,
                "lt": lt, "_eventId": "submit", "submit": "LOGIN"
            }
            r2 = self.session.post(action, data=payload, allow_redirects=False,
                                   headers={"Referer": cas_url}, timeout=15)
            loc = r2.headers.get("Location", "")
            if "ticket=ST-" not in loc:
                self.log.error("Login gagal: tidak ada ticket ST-")
                return False

            cur = loc
            for _ in range(6):
                r3 = self.session.get(cur, allow_redirects=False, timeout=15)
                if r3.status_code in (301, 302, 303, 307):
                    next_loc = r3.headers.get("Location", "")
                    if next_loc.startswith("/"):
                        parsed = urlparse(cur)
                        next_loc = f"{parsed.scheme}://{parsed.netloc}{next_loc}"
                    cur = next_loc
                    continue
                break

            self.log.info("✅ Login MIS berhasil")
            return True
        except Exception as e:
            self.log.error(f"Exception login MIS: {e}")
            return False

    def _ethol_sso(self) -> bool:
        self.log.info("SSO ETHOL...")
        try:
            r1 = self.session.get("https://ethol.pens.ac.id/api/auth/cas-redirect",
                                  allow_redirects=False, timeout=15)
            if r1.status_code not in (301, 302, 303, 307):
                return False

            cas_loc = r1.headers.get("Location", "")
            r2 = self.session.get(cas_loc, allow_redirects=False, timeout=15)
            if r2.status_code == 200:
                return False
            if r2.status_code not in (301, 302, 303, 307):
                return False

            cur = r2.headers.get("Location", "")
            if cur.startswith("/"):
                cur = "https://ethol.pens.ac.id" + cur

            for _ in range(6):
                r3 = self.session.get(cur, allow_redirects=False, timeout=15)
                if r3.status_code in (301, 302, 303, 307):
                    next_loc = r3.headers.get("Location", "")
                    if next_loc.startswith("/"):
                        next_loc = "https://ethol.pens.ac.id" + next_loc
                    cur = next_loc
                    continue
                break

            self.session.post("https://ethol.pens.ac.id/api/auth/refresh", json={}, timeout=15)
            rv = self.session.get("https://ethol.pens.ac.id/api/auth/validasi-token", timeout=15)
            if rv.status_code == 200:
                data = rv.json() or {}
                self.student_number = str(data.get("nomor", ""))
                self.student_name   = str(data.get("nama", ""))
                self.student_email  = str(data.get("email", ""))
                self.log.info(f"✅ SSO ETHOL berhasil. Nama: {self.student_name} | NRP: {self.student_number}")
                return True
            return False
        except Exception as e:
            self.log.error(f"Exception SSO: {e}")
            return False

    def verify(self) -> dict:
        """Verifikasi apakah kredensial akun valid di MIS CAS dan ETHOL PENS."""
        self.log.info(f"Verifikasi akun ETHOL untuk {self.user}...")
        if not self._mis_login():
            return {"success": False, "error": "Gagal login ke MIS CAS (Username/Password salah atau CAS PENS down)"}
        if not self._ethol_sso():
            return {"success": False, "error": "Gagal SSO ke ETHOL (Token SSO tidak valid)"}
        return {
            "success": True,
            "nomor": self.student_number,
            "nama": self.student_name,
            "email": self.student_email
        }

    def run_once(self):
        """Jalankan satu siklus cek dan submit presensi dengan fail-safe notification."""
        self.student_number = ""
        when = timestamp_str()

        # 1. Pengecekan Login MIS
        if not self._mis_login():
            self.log.error("Login MIS gagal, mengirim notifikasi peringatan ke mahasiswa...")
            log_to_firebase("MIS Login", "LOGIN_FAILED", f"Gagal login MIS CAS untuk akun {self.label}")
            msg = (
                f"⚠️ *PERINGATAN: Gagal Login MIS CAS*\n\n"
                f"👤 *Akun:* {self.label} ({self.user})\n"
                f"❌ *Kendala:* Autentikasi MIS CAS PENS ditolak (Password salah / Server Down).\n"
                f"⏰ *Waktu:* {when}\n\n"
                f"_Bot tidak dapat melakukan presensi otomatis. Segera cek kredensial atau presensi manual!_"
            )
            notify_client(self.config, msg)
            return

        # 2. Pengecekan SSO ETHOL
        if not self._ethol_sso():
            self.log.error("SSO ETHOL gagal, mengirim notifikasi peringatan ke mahasiswa...")
            log_to_firebase("ETHOL SSO", "SSO_FAILED", f"Gagal SSO ETHOL untuk akun {self.label}")
            msg = (
                f"⚠️ *PERINGATAN: Gagal SSO ETHOL*\n\n"
                f"👤 *Akun:* {self.label}\n"
                f"❌ *Kendala:* Sesi token SSO ETHOL tidak valid / server sibuk.\n"
                f"⏰ *Waktu:* {when}\n\n"
                f"_Segera buka https://ethol.pens.ac.id untuk melakukan presensi manual!_"
            )
            notify_client(self.config, msg)
            return

        # 3. Pengecekan Notifikasi & Eksekusi Presensi
        try:
            rn = self.session.get(
                "https://ethol.pens.ac.id/api/notifikasi/mahasiswa?filterNotif=PRESENSI",
                timeout=15
            )
            if rn.status_code != 200:
                self.log.info(f"Notif HTTP {rn.status_code}, lewati")
                return

            data_list = rn.json()
            if not isinstance(data_list, list) or len(data_list) == 0:
                self.log.info("Tidak ada notifikasi presensi")
                return

            notif = data_list[0]
            ket   = notif.get("keterangan", "")

            if "Dosen telah membuka presensi" not in ket:
                self.log.info("Tidak ada presensi yang dibuka")
                return

            data_terkait = notif.get("dataTerkait", "")
            if "-" not in data_terkait:
                return

            parts  = data_terkait.rsplit("-", 1)
            kuliah, js = parts[0].strip(), parts[1].strip()
            idx    = ket.find("untuk matakuliah ")
            matkul = ket[idx + 17:].strip() if idx >= 0 else ket.strip()
            self.log.info(f"📢 Presensi terbuka: {matkul} (Kuliah ID: {kuliah})")

            ra = self.session.get(
                f"https://ethol.pens.ac.id/api/presensi/aktif-kuliah?kuliah={kuliah}&jenis_schema={js}",
                timeout=15
            )
            if ra.status_code != 200:
                self.log.error(f"Gagal akses aktif-kuliah (HTTP {ra.status_code})")
                log_to_firebase(matkul, "API_ERROR", f"Gagal get aktif-kuliah HTTP {ra.status_code} untuk {self.label}")
                msg = (
                    f"⚠️ *Gagal Cek Sesi Presensi*\n\n"
                    f"👤 *Akun:* {self.label}\n"
                    f"📚 *Mata Kuliah:* {matkul}\n"
                    f"❌ *Kendala:* Server ETHOL merespons HTTP {ra.status_code}\n"
                    f"⏰ *Waktu:* {when}\n\n"
                    f"_Segera presensi manual di ETHOL!_"
                )
                notify_client(self.config, msg)
                return

            aktif_raw = ra.json()
            if isinstance(aktif_raw, list):
                aktif_data = aktif_raw[0] if aktif_raw else {}
            else:
                aktif_data = aktif_raw

            if aktif_data.get("open") != 1:
                self.log.info("Presensi belum aktif (LOCKED)")
                return

            # 4. Pengecekan Khusus Matakuliah 2 Mingguan (Sistem Kloter / Shift)
            manual_ids = get_manual_kuliah_ids()
            if str(kuliah) in manual_ids:
                self.log.info(f"Matakuliah {matkul} (ID {kuliah}) adalah jadwal 2 mingguan (Kloter). Mengirim peringatan manual...")
                log_to_firebase(matkul, "KLOTER_ALERT", f"Peringatan presensi kloter 2 mingguan dikirim ke {self.label} (Kuliah ID: {kuliah})")
                msg = (
                    f"📢 *PERINGATAN: Presensi Dibuka (Sistem Kloter 2 Minggu Sekali)*\n\n"
                    f"👤 *Akun:* {self.label}\n"
                    f"📚 *Mata Kuliah:* {matkul} (ID: {kuliah})\n"
                    f"⏰ *Waktu:* {when}\n\n"
                    f"⚠️ *Perhatian Khusus:*\n"
                    f"Mata kuliah ini berlangsung secara *2 minggu sekali (Sistem Kloter/Shift)*.\n"
                    f"Bot sengaja *tidak melakukan presensi otomatis* agar tidak salah absen di luar jadwal kloter Anda.\n\n"
                    f"👉 *Jika hari ini adalah jadwal kloter Anda, silakan segera lakukan presensi manual di ETHOL:*\n"
                    f"https://ethol.pens.ac.id"
                )
                notify_client(self.config, msg)
                return

            # 5. Pengecekan Kunci Presensi
            key = aktif_data.get("key", "")
            if not key or not self.student_number:
                self.log.warning("Key presensi kosong atau student_number tidak ada")
                log_to_firebase(matkul, "KEY_EMPTY", f"Key presensi kosong untuk {self.label}")
                msg = (
                    f"⚠️ *Presensi Terbuka tapi Kunci Belum Ada*\n\n"
                    f"👤 *Akun:* {self.label}\n"
                    f"📚 *Mata Kuliah:* {matkul}\n"
                    f"⏰ *Waktu:* {when}\n\n"
                    f"_Kunci presensi belum tersedia di server. Harap presensi manual di web ETHOL._"
                )
                notify_client(self.config, msg)
                return

            # 6. Submit Presensi ke ETHOL
            payload = {
                "kuliah": int(kuliah), "jenis_schema": int(js),
                "mahasiswa": int(self.student_number),
                "key": key, "kuliah_asal": int(kuliah)
            }
            rs      = self.session.post("https://ethol.pens.ac.id/api/presensi/mahasiswa",
                                        json=payload, timeout=15)
            rs_data = rs.json() if "application/json" in rs.headers.get("content-type","") else {}
            sukses  = rs.status_code == 200 and rs_data.get("sukses") is True
            pesan   = rs_data.get("pesan", "")

            self.log.info(f"Submit HTTP {rs.status_code} sukses={sukses} pesan={pesan}")

            if sukses:
                log_to_firebase(matkul, "SUCCESS", f"Presensi berhasil untuk {self.label}")
                msg = (
                    f"✅ *Presensi Berhasil!*\n\n"
                    f"👤 *Akun:* {self.label}\n"
                    f"📚 *Mata Kuliah:* {matkul}\n"
                    f"⏰ *Waktu:* {when}\n\n"
                    f"_Presensi otomatis via ETHOL Bot._"
                )
                notify_client(self.config, msg)
            elif is_already_present_msg(pesan):
                # Client sudah melakukan presensi manual sebelumnya
                log_to_firebase(matkul, "ALREADY_PRESENT", f"Akun {self.label} sudah presensi manual ({pesan})")
                msg = (
                    f"ℹ️ *Status: Sudah Melakukan Presensi Manual*\n\n"
                    f"👤 *Akun:* {self.label}\n"
                    f"📚 *Mata Kuliah:* {matkul}\n"
                    f"⏰ *Waktu:* {when}\n\n"
                    f"_{pesan or 'Anda telah tercatat melakukan presensi secara manual sebelumnya.'}_\n"
                    f"_Tidak perlu melakukan presensi ulang._"
                )
                notify_client(self.config, msg)
            else:
                log_to_firebase(matkul, "FAILED", f"Gagal presensi {self.label}: {pesan}")
                msg = (
                    f"⚠️ *Gagal Presensi Otomatis*\n\n"
                    f"👤 *Akun:* {self.label}\n"
                    f"📚 *Mata Kuliah:* {matkul}\n"
                    f"⏰ *Waktu:* {when}\n\n"
                    f"_{pesan or 'server menolak submit presensi'} — segera lakukan presensi manual!_"
                )
                notify_client(self.config, msg)
        except Exception as e:
            self.log.error(f"Exception run_once: {e}")
            log_to_firebase("System Worker", "EXCEPTION", f"Worker error pada {self.label}: {str(e)[:100]}")
            msg = (
                f"⚠️ *Kendala Presensi Otomatis*\n\n"
                f"👤 *Akun:* {self.label}\n"
                f"❌ *Kendala:* Gangguan koneksi / runtime ({type(e).__name__})\n"
                f"⏰ *Waktu:* {when}\n\n"
                f"_Segera buka https://ethol.pens.ac.id untuk presensi manual._"
            )
            notify_client(self.config, msg)


def handle_verification(target_user: str = ""):
    """Menjalankan verifikasi akun ETHOL / MIS dan menyimpan statusnya ke Firebase."""
    logging.info(f"=== Menjalankan Verifikasi Akun ETHOL (Target: {target_user or 'Semua Akun'}) ===")

    try:
        r = requests.get(f"{FIREBASE_URL}/accounts.json", timeout=10)
        raw_data = r.json() if r.status_code == 200 else []
        accounts_list = raw_data if isinstance(raw_data, list) else (list(raw_data.values()) if isinstance(raw_data, dict) else [])
    except Exception as e:
        logging.error(f"Gagal mengambil accounts dari Firebase: {e}")
        return

    verified_count = 0
    last_result = {}

    for acc in accounts_list:
        user = acc.get("user", "")
        if target_user and target_user.lower() not in ("all", "") and user.lower() != target_user.lower():
            continue

        worker = AccountWorker(acc)
        res = worker.verify()
        when = timestamp_str()

        if res["success"]:
            verified_count += 1
            acc["verified"] = True
            acc["nrp"] = res["nomor"]
            acc["official_name"] = res["nama"]
            acc["last_verified"] = when
            acc["verify_status"] = "OK"
            acc["verify_message"] = "Akun Valid & Terverifikasi"
            last_result = {
                "status": "SUCCESS",
                "user": user,
                "nama": res["nama"],
                "nrp": res["nomor"],
                "timestamp": when
            }
            log_to_firebase("Verifikasi Akun", "VERIFIED_OK", f"Akun {user} valid. Nama: {res['nama']}, NRP: {res['nomor']}")
        else:
            acc["verified"] = False
            acc["last_verified"] = when
            acc["verify_status"] = "FAILED"
            acc["verify_message"] = res["error"]
            last_result = {
                "status": "FAILED",
                "user": user,
                "error": res["error"],
                "timestamp": when
            }
            log_to_firebase("Verifikasi Akun", "VERIFIED_FAIL", f"Akun {user} gagal verifikasi: {res['error']}")

    try:
        requests.put(f"{FIREBASE_URL}/accounts.json", json=accounts_list, timeout=10)
        if last_result:
            requests.put(f"{FIREBASE_URL}/verify_result.json", json=last_result, timeout=10)
        requests.put(f"{FIREBASE_URL}/verify_request/status.json", json="DONE", timeout=10)
        logging.info(f"✅ Selesai verifikasi akun (Berhasil: {verified_count}/{len(accounts_list)}).")
    except Exception as e:
        logging.error(f"Gagal simpan hasil verifikasi ke Firebase: {e}")


def run_worker(config):
    AccountWorker(config).run_once()


def main():
    # 1. Cek apakah ada request verifikasi akun (dari Event Payload, Env, atau Firebase)
    client_payload_raw = os.environ.get("CLIENT_PAYLOAD", "{}")
    event_action = os.environ.get("GITHUB_EVENT_ACTION", "")
    try:
        payload = json.loads(client_payload_raw) if client_payload_raw else {}
    except Exception:
        payload = {}

    target_user = payload.get("target_user") or os.environ.get("TARGET_USER", "")
    action = payload.get("action") or event_action

    # Cek juga dari Firebase verify_request jika pending
    if not target_user and not action:
        try:
            r = requests.get(f"{FIREBASE_URL}/verify_request.json", timeout=5)
            if r.status_code == 200 and r.json():
                req = r.json()
                if req.get("status") == "PENDING":
                    action = "verify"
                    target_user = req.get("user", "all")
        except Exception:
            pass

    if action in ("verify", "ethol_verify_account"):
        handle_verification(target_user)
        return

    # 2. Jalankan Cloud Watchdog untuk kesehatan ESP32
    check_esp32_offline_watchdog()

    # 3. Proses presensi multi-akun aktif
    accounts = get_active_accounts()
    if not accounts:
        logging.warning("Tidak ada akun aktif di Firebase / ACCOUNTS_JSON!")
        return

    logging.info(f"=== ETHOL Cloud Worker - {len(accounts)} Akun Aktif | {now_wib().strftime('%d-%m-%Y %H:%M WIB')} ===")

    threads = []
    for acc in accounts:
        t = threading.Thread(target=run_worker, args=(acc,), name=acc.get("name", acc["user"].split("@")[0]))
        t.start()
        threads.append(t)
        time.sleep(2)

    for t in threads:
        t.join(timeout=120)

    logging.info("=== Semua Akun Selesai Diproses ===")


if __name__ == "__main__":
    main()
