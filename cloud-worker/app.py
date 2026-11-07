"""
ETHOL Presensi Bot - Local Standalone Multi-Account Worker
Menjalankan presensi otomatis dari perangkat lokal/server mandiri (tanpa ESP32).
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

FONNTE_TOKEN  = os.environ.get("FONNTE_TOKEN", "YOUR_FONNTE_TOKEN")
ACCOUNTS_JSON = os.environ.get("ACCOUNTS_JSON", "[]")

POLL_INTERVAL  = int(os.environ.get("POLL_INTERVAL", "20"))
JAM_MULAI      = int(os.environ.get("JAM_MULAI", "6"))
JAM_SELESAI    = int(os.environ.get("JAM_SELESAI", "21"))

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

def is_already_present_msg(msg_str: str) -> bool:
    if not msg_str:
        return False
    lower = msg_str.lower()
    return ("sudah" in lower and any(w in lower for w in ["presensi", "absen", "isi", "mengisi", "ada", "tercatat", "terdaftar"])) or ("already" in lower)

def send_wa(target: str, message: str) -> bool:
    if not FONNTE_TOKEN or not target:
        return False
    try:
        r = requests.post(
            "https://api.fonnte.com/send",
            headers={"Authorization": FONNTE_TOKEN},
            json={"target": target, "message": message},
            timeout=15
        )
        ok = r.status_code == 200 and r.json().get("status") is True
        logging.getLogger("FONNTE").info(f"{'✅' if ok else '❌'} WA ke {target}: HTTP {r.status_code}")
        return ok
    except Exception as e:
        logging.getLogger("FONNTE").error(f"Gagal kirim WA: {e}")
        return False


class AccountWorker:
    def __init__(self, config: dict, startup_delay: float = 0.0):
        self.config        = config
        self.user          = config["user"]
        self.password      = config["pass"]
        self.wa_target     = config.get("wa_target", "")
        self.label         = config.get("name", self.user.split("@")[0])
        self.startup_delay = startup_delay
        self.log           = logging.getLogger(self.label)
        self.session       = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0 (EtholBot/2.0)"})
        self.student_number = ""
        self.seen_today     = set()

    def _login_ethol_sso(self) -> bool:
        """Melakukan autentikasi SSO CAS resmi langsung ke server ETHOL PENS."""
        self.log.info("Autentikasi SSO ETHOL via CAS...")
        try:
            # 1. Inisiasi alur SSO CAS langsung dari endpoint resmi ETHOL
            r1 = self.session.get("https://ethol.pens.ac.id/api/auth/cas-redirect",
                                  allow_redirects=False, timeout=15)
            cas_login_url = r1.headers.get("Location", "")
            if not cas_login_url:
                self.log.error("Gagal mendapatkan redirect CAS dari ETHOL")
                return False

            # 2. Ambil halaman login CAS untuk mendapatkan token lt dan URL action
            r2 = self.session.get(cas_login_url, allow_redirects=False, timeout=15)
            body = r2.text
            lt_match = re.search(r'name="lt"\s+value="([^"]+)"', body)
            action_match = re.search(r'action="([^"]+)"', body)
            if not lt_match or not action_match:
                self.log.error("Token lt / action form tidak ditemukan pada CAS PENS")
                return False

            lt = lt_match.group(1)
            action = action_match.group(1)
            if action.startswith("/"):
                parsed = urlparse(cas_login_url)
                action = f"{parsed.scheme}://{parsed.netloc}{action}"

            # 3. Kirim kredensial akun mahasiswa ke CAS PENS
            payload = {
                "username": self.user,
                "password": self.password,
                "lt": lt,
                "_eventId": "submit",
                "submit": "LOGIN"
            }
            r3 = self.session.post(action, data=payload, allow_redirects=False,
                                   headers={"Referer": cas_login_url}, timeout=15)
            callback_url = r3.headers.get("Location", "")
            if not callback_url or "ticket=ST-" not in callback_url:
                self.log.error("Autentikasi CAS gagal: Username / Password salah")
                return False

            # 4. Ikuti callback tiket ST- kembali ke sistem ETHOL
            cur = callback_url
            if cur.startswith("/"):
                cur = "https://ethol.pens.ac.id" + cur

            for _ in range(6):
                rc = self.session.get(cur, allow_redirects=False, timeout=15)
                if rc.status_code in (301, 302, 303, 307):
                    nxt = rc.headers.get("Location", "")
                    if nxt.startswith("/"):
                        nxt = "https://ethol.pens.ac.id" + nxt
                    cur = nxt
                    continue
                break

            # 5. Refresh token & Validasi token ETHOL
            self.session.post("https://ethol.pens.ac.id/api/auth/refresh", json={}, timeout=15)
            rv = self.session.get("https://ethol.pens.ac.id/api/auth/validasi-token", timeout=15)
            if rv.status_code == 200:
                self.student_number = str(rv.json().get("nomor", ""))
                self.log.info(f"✅ SSO ETHOL berhasil, no={self.student_number}")
                return True

            self.log.error(f"Validasi token ETHOL gagal (HTTP {rv.status_code})")
            return False
        except Exception as e:
            self.log.error(f"Exception SSO ETHOL: {e}")
            return False

    def check_and_presensi(self):
        try:
            rn = self.session.get(
                "https://ethol.pens.ac.id/api/notifikasi/mahasiswa?filterNotif=PRESENSI",
                timeout=15
            )
            if rn.status_code != 200:
                return

            data_list = rn.json()
            if not isinstance(data_list, list) or len(data_list) == 0:
                return

            notif = data_list[0]
            ket   = notif.get("keterangan", "")
            if "Dosen telah membuka presensi" not in ket:
                return

            data_terkait = notif.get("dataTerkait", "")
            if "-" not in data_terkait:
                return

            parts  = data_terkait.rsplit("-", 1)
            kuliah, js = parts[0].strip(), parts[1].strip()
            idx    = ket.find("untuk matakuliah ")
            matkul = ket[idx + 17:].strip() if idx >= 0 else ket.strip()
            ds     = date_stamp()

            ra = self.session.get(
                f"https://ethol.pens.ac.id/api/presensi/aktif-kuliah?kuliah={kuliah}&jenis_schema={js}",
                timeout=15
            )
            if ra.status_code != 200:
                return

            aktif_data = ra.json()
            if isinstance(aktif_data, list):
                aktif_data = aktif_data[0] if aktif_data else {}

            if aktif_data.get("open") != 1:
                return

            # Pengecekan Matakuliah 2 Mingguan (Kloter)
            if str(kuliah) in DEFAULT_MANUAL_KULIAH_IDS:
                seen_key = f"{kuliah}_{ds}"
                if seen_key in self.seen_today:
                    return
                self.seen_today.add(seen_key)
                msg = (
                    f"📢 *PERINGATAN: Presensi Dibuka (Sistem Kloter 2 Minggu Sekali)*\n\n"
                    f"👤 *Akun:* {self.label}\n"
                    f"📚 *Mata Kuliah:* {matkul} (ID: {kuliah})\n"
                    f"⏰ *Waktu:* {timestamp_str()}\n\n"
                    f"⚠️ Kuliah ini berlangsung 2 minggu sekali. Silakan presensi manual di ETHOL jika ini adalah kloter Anda:\n"
                    f"https://ethol.pens.ac.id"
                )
                send_wa(self.wa_target, msg)
                return

            key = aktif_data.get("key", "")
            if not key or not self.student_number:
                return

            seen_key = f"{kuliah}_{ds}"
            if seen_key in self.seen_today:
                return
            self.seen_today.add(seen_key)

            payload = {
                "kuliah": int(kuliah), "jenis_schema": int(js),
                "mahasiswa": int(self.student_number),
                "key": key, "kuliah_asal": int(kuliah)
            }
            rs      = self.session.post("https://ethol.pens.ac.id/api/presensi/mahasiswa",
                                        json=payload, timeout=15)
            when    = timestamp_str()
            rs_data = rs.json() if "application/json" in rs.headers.get("content-type","") else {}
            sukses  = rs.status_code == 200 and rs_data.get("sukses") is True
            pesan   = rs_data.get("pesan", "")

            if sukses:
                msg = (
                    f"✅ *Presensi Berhasil!*\n\n"
                    f"👤 *Akun:* {self.label}\n"
                    f"📚 *Mata Kuliah:* {matkul}\n"
                    f"⏰ *Waktu:* {when}\n\n"
                    f"_Presensi otomatis via ETHOL Bot._"
                )
                send_wa(self.wa_target, msg)
            elif is_already_present_msg(pesan):
                msg = (
                    f"ℹ️ *Status: Sudah Melakukan Presensi Manual*\n\n"
                    f"👤 *Akun:* {self.label}\n"
                    f"📚 *Mata Kuliah:* {matkul}\n"
                    f"⏰ *Waktu:* {when}\n\n"
                    f"_{pesan or 'Anda telah tercatat presensi manual sebelumnya.'}_"
                )
                send_wa(self.wa_target, msg)
            else:
                msg = (
                    f"⚠️ *Gagal Presensi Otomatis*\n\n"
                    f"👤 *Akun:* {self.label}\n"
                    f"📚 *Mata Kuliah:* {matkul}\n"
                    f"⏰ *Waktu:* {when}\n\n"
                    f"_{pesan or 'server menolak'} — segera presensi manual di ETHOL!_"
                )
                send_wa(self.wa_target, msg)
        except Exception as e:
            self.log.error(f"Exception presensi: {e}")

    def run(self):
        if self.startup_delay > 0:
            time.sleep(self.startup_delay)

        self.log.info(f"=== Worker [{self.label}] dimulai ===")
        self._login_ethol_sso()

        while True:
            try:
                if in_window():
                    self.check_and_presensi()
                else:
                    self.log.info("Di luar jam perkuliahan, standby...")
            except Exception as e:
                self.log.error(f"Loop error: {e}")
            time.sleep(POLL_INTERVAL)


def main():
    try:
        raw_acc = json.loads(ACCOUNTS_JSON)
    except Exception:
        raw_acc = []

    if not raw_acc:
        logging.warning("ACCOUNTS_JSON kosong! Masukkan daftar akun di environment.")
        return

    threads = []
    for i, acc in enumerate(raw_acc):
        if not acc.get("is_active", True):
            continue
        delay = i * 2.0
        worker = AccountWorker(acc, startup_delay=delay)
        t = threading.Thread(target=worker.run, name=worker.label, daemon=True)
        t.start()
        threads.append(t)

    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
