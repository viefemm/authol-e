"""
ETHOL Presensi Bot - Mode GitHub Actions (Single Run)
Script ini dirancang untuk dijalankan sekali per eksekusi (tidak loop).
GitHub Actions akan memanggil script ini setiap 5 menit via cron.
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

FONNTE_TOKEN  = os.environ.get("FONNTE_TOKEN", "")
ACCOUNTS_JSON = os.environ.get("ACCOUNTS_JSON", "[]")
ACCOUNTS      = json.loads(ACCOUNTS_JSON)
JAM_MULAI     = int(os.environ.get("JAM_MULAI", "6"))
JAM_SELESAI   = int(os.environ.get("JAM_SELESAI", "21"))


def now_wib() -> datetime:
    return datetime.now(WIB)

def in_window() -> bool:
    n = now_wib()
    return n.weekday() < 5 and JAM_MULAI <= n.hour < JAM_SELESAI

def timestamp_str() -> str:
    return now_wib().strftime("%d-%m-%Y pukul %H:%M WIB")

def date_stamp() -> str:
    return now_wib().strftime("%Y%m%d")

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
        logging.getLogger("FONNTE").info(f"{'OK' if ok else 'GAGAL'} WA ke {target}: HTTP {r.status_code}")
        return ok
    except Exception as e:
        logging.getLogger("FONNTE").error(f"Gagal kirim WA: {e}")
        return False


class AccountWorker:
    def __init__(self, config: dict):
        self.user       = config["user"]
        self.password   = config["pass"]
        self.wa_target  = config.get("wa_target", "")
        self.label      = self.user.split("@")[0]
        self.log        = logging.getLogger(self.label)
        self.session    = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0 (EtholBot/2.0)"})

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
                self.student_number = str(rv.json().get("nomor", ""))
                self.log.info(f"✅ SSO ETHOL berhasil. Nomor: {self.student_number}")
                return True
            return False
        except Exception as e:
            self.log.error(f"Exception SSO: {e}")
            return False

    def run_once(self):
        """Jalankan satu siklus cek presensi (untuk GitHub Actions)."""
        self.student_number = ""

        if not self._mis_login():
            self.log.error("Login MIS gagal, skip akun ini")
            return
        if not self._ethol_sso():
            self.log.error("SSO ETHOL gagal, skip akun ini")
            return

        ds = date_stamp()
        try:
            rn = self.session.get(
                "https://ethol.pens.ac.id/api/notifikasi/mahasiswa?filterNotif=PRESENSI",
                timeout=15
            )
            if rn.status_code != 200:
                self.log.info(f"Notif HTTP {rn.status_code}, skip")
                return

            data_list = rn.json()
            if not isinstance(data_list, list) or len(data_list) == 0:
                self.log.info("Tidak ada notifikasi presensi")
                return

            notif    = data_list[0]
            id_notif = str(notif.get("idNotifikasi", ""))
            ket      = notif.get("keterangan", "")

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
            self.log.info(f"📢 Presensi terbuka: {matkul}")

            ra = self.session.get(
                f"https://ethol.pens.ac.id/api/presensi/aktif-kuliah?kuliah={kuliah}&jenis_schema={js}",
                timeout=15
            )
            if ra.status_code != 200:
                return

            aktif_raw = ra.json()
            # Response bisa berupa dict atau list of dict
            if isinstance(aktif_raw, list):
                aktif_data = aktif_raw[0] if aktif_raw else {}
            else:
                aktif_data = aktif_raw

            if aktif_data.get("open") != 1:
                self.log.info("Presensi belum aktif (LOCKED)")
                return

            key = aktif_data.get("key", "")
            if not key or not self.student_number:
                return

            payload = {
                "kuliah": int(kuliah), "jenis_schema": int(js),
                "mahasiswa": int(self.student_number),
                "key": key, "kuliah_asal": int(kuliah)
            }
            rs     = self.session.post("https://ethol.pens.ac.id/api/presensi/mahasiswa",
                                       json=payload, timeout=15)
            rs_data = rs.json() if "application/json" in rs.headers.get("content-type","") else {}
            sukses  = rs.status_code == 200 and rs_data.get("sukses") is True
            pesan   = rs_data.get("pesan", "")
            when    = timestamp_str()

            self.log.info(f"Submit HTTP {rs.status_code} sukses={sukses} pesan={pesan}")

            if sukses:
                send_wa(self.wa_target, (
                    f"✅ *Presensi Berhasil!*\n\n"
                    f"👤 *Akun:* {self.label}\n"
                    f"📚 *Mata Kuliah:* {matkul}\n"
                    f"⏰ *Waktu:* {when}\n\n"
                    f"_Presensi otomatis via ETHOL Bot._"
                ))
            else:
                send_wa(self.wa_target, (
                    f"⚠️ *Gagal Presensi Otomatis*\n\n"
                    f"👤 *Akun:* {self.label}\n"
                    f"📚 *Mata Kuliah:* {matkul}\n"
                    f"⏰ *Waktu:* {when}\n\n"
                    f"_{pesan or 'server tidak memberi pesan'} — segera presensi manual._"
                ))
        except Exception as e:
            self.log.error(f"Exception run_once: {e}")


def run_worker(config):
    AccountWorker(config).run_once()


def main():
    if not in_window():
        logging.info(f"Di luar jadwal ({now_wib().strftime('%A %H:%M WIB')}), tidak ada yang dilakukan.")
        return

    if not ACCOUNTS:
        logging.error("ACCOUNTS_JSON kosong!")
        return

    logging.info(f"=== ETHOL Bot - {len(ACCOUNTS)} akun | {now_wib().strftime('%d-%m-%Y %H:%M WIB')} ===")

    threads = []
    for i, acc in enumerate(ACCOUNTS):
        t = threading.Thread(target=run_worker, args=(acc,), name=acc["user"].split("@")[0])
        t.start()
        threads.append(t)
        time.sleep(3)  # stagger 3 detik antar akun

    for t in threads:
        t.join(timeout=120)

    logging.info("=== Selesai ===")


if __name__ == "__main__":
    main()
