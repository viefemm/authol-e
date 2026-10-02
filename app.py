"""
ETHOL Presensi Bot - Multi Account
Deploy di Render.com sebagai Background Worker
"""

import os
import time
import json
import logging
import threading
import requests
from datetime import datetime
import pytz

# ── Logging Setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

WIB = pytz.timezone("Asia/Jakarta")

# ── Konfigurasi dari Environment Variables ────────────────────────────────────
FONNTE_TOKEN  = os.environ.get("FONNTE_TOKEN", "")
ACCOUNTS_JSON = os.environ.get("ACCOUNTS_JSON", "[]")
ACCOUNTS      = json.loads(ACCOUNTS_JSON)

# Interval polling dalam detik (default: 20 detik)
POLL_INTERVAL  = int(os.environ.get("POLL_INTERVAL", "20"))
JAM_MULAI      = int(os.environ.get("JAM_MULAI", "6"))
JAM_SELESAI    = int(os.environ.get("JAM_SELESAI", "21"))


# ── Helper: Waktu WIB ─────────────────────────────────────────────────────────
def now_wib() -> datetime:
    return datetime.now(WIB)

def in_window() -> bool:
    """Cek apakah sekarang dalam jadwal Senin-Jumat jam JAM_MULAI - JAM_SELESAI WIB."""
    n = now_wib()
    return n.weekday() < 5 and JAM_MULAI <= n.hour < JAM_SELESAI

def timestamp_str() -> str:
    n = now_wib()
    return n.strftime("%d-%m-%Y pukul %H:%M WIB")

def date_stamp() -> str:
    return now_wib().strftime("%Y%m%d")


# ── Helper: Fonnte WhatsApp ───────────────────────────────────────────────────
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
        logging.getLogger("FONNTE").info(
            f"{'✅' if ok else '❌'} WA ke {target}: HTTP {r.status_code}"
        )
        return ok
    except Exception as e:
        logging.getLogger("FONNTE").error(f"Gagal kirim WA: {e}")
        return False


# ── Kelas Utama: Worker Per Akun ──────────────────────────────────────────────
class AccountWorker:
    def __init__(self, config: dict, startup_delay: float = 0):
        self.user        = config["user"]
        self.password    = config["pass"]
        self.wa_target   = config.get("wa_target", "")
        self.label       = self.user.split("@")[0]
        self.log         = logging.getLogger(self.label)
        self.session     = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0 (EtholBot/2.0)"})
        self.startup_delay   = startup_delay
        self.student_number  = ""
        self.last_notif_id   = ""
        self.seen_today: set = set()
        self.last_date_stamp = ""

    # ── MIS CAS Login ─────────────────────────────────────────────────────────
    def _mis_login(self) -> bool:
        self.log.info("Login MIS CAS...")
        try:
            # 1. Landing page, ikuti redirect manual
            cas_url = "https://online.mis.pens.ac.id/index.php?Login=1&halAwal=1"
            body = ""
            for _ in range(6):
                r = self.session.get(cas_url, allow_redirects=False, timeout=15)
                self.log.info(f"  GET {cas_url} -> {r.status_code}")
                if r.status_code in (301, 302, 303, 307):
                    cas_url = r.headers.get("Location", cas_url)
                    if cas_url.startswith("/"):
                        cas_url = "https://login.pens.ac.id" + cas_url
                    continue
                if r.status_code == 200:
                    body = r.text
                break

            if not body:
                self.log.error("Login gagal: body kosong")
                return False

            # 2. Parse lt & action dari form CAS
            import re
            lt_match     = re.search(r'name="lt"\s+value="([^"]+)"', body)
            action_match = re.search(r'action="([^"]+)"', body)
            if not lt_match or not action_match:
                self.log.error("Login gagal: lt/action tidak ditemukan di form")
                return False

            lt     = lt_match.group(1)
            action = action_match.group(1)
            if action.startswith("/"):
                # action relatif ke CAS host
                from urllib.parse import urlparse
                parsed = urlparse(cas_url)
                action = f"{parsed.scheme}://{parsed.netloc}{action}"
            self.log.info(f"  lt={lt[:10]}... action={action}")

            # 3. POST ke CAS
            payload = {
                "username": self.user,
                "password": self.password,
                "lt":       lt,
                "_eventId": "submit",
                "submit":   "LOGIN"
            }
            r2 = self.session.post(
                action, data=payload, allow_redirects=False,
                headers={"Referer": cas_url}, timeout=15
            )
            self.log.info(f"  POST CAS -> {r2.status_code} Location={r2.headers.get('Location','')[:80]}")

            loc = r2.headers.get("Location", "")
            if "ticket=ST-" not in loc:
                self.log.error("Login gagal: tidak ada ticket ST-")
                return False

            # 4. Tukar ticket - ikuti redirect sampai habis
            cur = loc
            for _ in range(6):
                r3 = self.session.get(cur, allow_redirects=False, timeout=15)
                self.log.info(f"  TUKAR {cur[:60]} -> {r3.status_code}")
                if r3.status_code in (301, 302, 303, 307):
                    next_loc = r3.headers.get("Location", "")
                    if next_loc.startswith("/"):
                        from urllib.parse import urlparse
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

    # ── ETHOL SSO ─────────────────────────────────────────────────────────────
    def _ethol_sso(self) -> bool:
        self.log.info("SSO ETHOL via CAS...")
        try:
            # 1. Minta CAS redirect dari ETHOL
            r1 = self.session.get(
                "https://ethol.pens.ac.id/api/auth/cas-redirect",
                allow_redirects=False, timeout=15
            )
            self.log.info(f"  cas-redirect -> {r1.status_code}")
            if r1.status_code not in (301, 302, 303, 307):
                self.log.error("SSO gagal: cas-redirect tidak redirect")
                return False

            cas_loc = r1.headers.get("Location", "")

            # 2. Hit CAS dengan cookie MIS (session sudah punya CASTGC)
            r2 = self.session.get(cas_loc, allow_redirects=False, timeout=15)
            self.log.info(f"  CAS -> {r2.status_code} Location={r2.headers.get('Location','')[:80]}")
            if r2.status_code == 200:
                self.log.error("SSO gagal: CAS minta login ulang")
                return False
            if r2.status_code not in (301, 302, 303, 307):
                self.log.error("SSO gagal: CAS tidak balik ke ETHOL")
                return False

            # 3. Ikuti redirect kembali ke ETHOL dengan cookie ETHOL
            cur = r2.headers.get("Location", "")
            if cur.startswith("/"):
                cur = "https://ethol.pens.ac.id" + cur

            for _ in range(6):
                r3 = self.session.get(cur, allow_redirects=False, timeout=15)
                self.log.info(f"  ETHOL CB -> {r3.status_code}")
                if r3.status_code in (301, 302, 303, 307):
                    next_loc = r3.headers.get("Location", "")
                    if next_loc.startswith("/"):
                        next_loc = "https://ethol.pens.ac.id" + next_loc
                    cur = next_loc
                    continue
                break

            # 4. Refresh token lalu validasi
            self.session.post(
                "https://ethol.pens.ac.id/api/auth/refresh",
                json={}, timeout=15
            )
            rv = self.session.get(
                "https://ethol.pens.ac.id/api/auth/validasi-token",
                timeout=15
            )
            if rv.status_code == 200:
                data = rv.json()
                self.student_number = str(data.get("nomor", ""))
                self.log.info(f"✅ SSO ETHOL berhasil. Nomor: {self.student_number}")
                return True
            else:
                self.log.error(f"SSO ETHOL gagal: validasi-token {rv.status_code}")
                return False

        except Exception as e:
            self.log.error(f"Exception SSO ETHOL: {e}")
            return False

    # ── Ensure Session ────────────────────────────────────────────────────────
    def _ensure_session(self) -> bool:
        """Validasi sesi, jika gagal re-auth dari awal."""
        try:
            rv = self.session.get(
                "https://ethol.pens.ac.id/api/auth/validasi-token", timeout=15
            )
            if rv.status_code == 200:
                data = rv.json()
                self.student_number = str(data.get("nomor", self.student_number))
                return True
        except Exception:
            pass

        # Coba refresh dulu
        try:
            rr = self.session.post(
                "https://ethol.pens.ac.id/api/auth/refresh", json={}, timeout=15
            )
            if rr.status_code == 200:
                rv2 = self.session.get(
                    "https://ethol.pens.ac.id/api/auth/validasi-token", timeout=15
                )
                if rv2.status_code == 200:
                    return True
        except Exception:
            pass

        # Full re-auth
        self.log.info("Sesi habis, full re-auth...")
        if self._mis_login():
            return self._ethol_sso()
        return False

    # ── Cek & Submit Presensi ─────────────────────────────────────────────────
    def _check_presensi(self):
        ds = date_stamp()
        if ds != self.last_date_stamp:
            self.seen_today.clear()
            self.last_date_stamp = ds

        try:
            # 1. Ambil notifikasi presensi terbaru
            rn = self.session.get(
                "https://ethol.pens.ac.id/api/notifikasi/mahasiswa?filterNotif=PRESENSI",
                timeout=15
            )
            if rn.status_code == 401:
                self.log.info("401 - sesi habis, re-auth...")
                if self._ensure_session():
                    rn = self.session.get(
                        "https://ethol.pens.ac.id/api/notifikasi/mahasiswa?filterNotif=PRESENSI",
                        timeout=15
                    )
                else:
                    return

            if rn.status_code != 200:
                return

            data_list = rn.json()
            if not isinstance(data_list, list) or len(data_list) == 0:
                return

            # Notif terbaru di index 0
            notif     = data_list[0]
            id_notif  = str(notif.get("idNotifikasi", ""))
            ket       = notif.get("keterangan", "")

            if "Dosen telah membuka presensi" not in ket:
                return
            if id_notif == self.last_notif_id:
                return  # Tidak ada notif baru

            self.last_notif_id = id_notif

            # Parse kuliah dan jenis_schema dari dataTerkait (format: "123456-4")
            data_terkait = notif.get("dataTerkait", "")
            if "-" not in data_terkait:
                return

            parts = data_terkait.rsplit("-", 1)
            kuliah, js = parts[0].strip(), parts[1].strip()

            # Parse nama matkul
            idx = ket.find("untuk matakuliah ")
            matkul = ket[idx + 17:].strip() if idx >= 0 else ket.strip()
            self.log.info(f"📢 NOTIF BARU: {matkul} | kuliah={kuliah} js={js}")

            # 2. Cek apakah sesi aktif (open=1)
            ra = self.session.get(
                f"https://ethol.pens.ac.id/api/presensi/aktif-kuliah?kuliah={kuliah}&jenis_schema={js}",
                timeout=15
            )
            if ra.status_code == 401:
                if not self._ensure_session():
                    return
                ra = self.session.get(
                    f"https://ethol.pens.ac.id/api/presensi/aktif-kuliah?kuliah={kuliah}&jenis_schema={js}",
                    timeout=15
                )

            if ra.status_code != 200:
                return

            aktif_data = ra.json()
            if not aktif_data.get("open") == 1:
                self.log.info("Sesi belum aktif (LOCKED)")
                return

            key = aktif_data.get("key", "")
            if not key:
                self.log.info("Sesi aktif tapi key kosong")
                return

            self.log.info(f"🔓 Sesi AKTIF, key={key[:8]}...")

            # 3. Cek sudah diproses hari ini
            seen_key = f"{kuliah}_{ds}"
            if seen_key in self.seen_today:
                self.log.info("Sudah diproses hari ini, lewati")
                return
            self.seen_today.add(seen_key)

            if not self.student_number:
                self.log.error("Nomor mahasiswa belum diketahui, lewati")
                return

            # 4. Submit presensi
            payload = {
                "kuliah":       int(kuliah),
                "jenis_schema": int(js),
                "mahasiswa":    int(self.student_number),
                "key":          key,
                "kuliah_asal":  int(kuliah)
            }
            rs = self.session.post(
                "https://ethol.pens.ac.id/api/presensi/mahasiswa",
                json=payload, timeout=15
            )
            when = timestamp_str()
            rs_data   = rs.json() if rs.headers.get("content-type","").startswith("application/json") else {}
            sukses    = rs.status_code == 200 and rs_data.get("sukses") is True
            pesan     = rs_data.get("pesan", "")

            self.log.info(f"  Submit HTTP {rs.status_code} sukses={sukses} pesan={pesan}")

            if sukses:
                msg = (
                    f"✅ *Presensi Berhasil!*\n\n"
                    f"👤 *Akun:* {self.label}\n"
                    f"📚 *Mata Kuliah:* {matkul}\n"
                    f"⏰ *Waktu:* {when}\n\n"
                    f"_Sistem telah berhasil melakukan presensi otomatis di ETHOL._"
                )
                send_wa(self.wa_target, msg)
            else:
                detail = f"HTTP {rs.status_code} | pesan={pesan} | body={rs.text[:120]}"
                msg = (
                    f"⚠️ *Gagal Presensi Otomatis*\n\n"
                    f"👤 *Akun:* {self.label}\n"
                    f"📚 *Mata Kuliah:* {matkul}\n"
                    f"⏰ *Waktu:* {when}\n\n"
                    f"_{pesan or 'server tidak memberi pesan'} — segera presensi manual._\n\n"
                    f"🛠 *Diagnostik:*\n```\n{detail}\n```"
                )
                send_wa(self.wa_target, msg)

        except Exception as e:
            self.log.error(f"Exception cek presensi: {e}")

    # ── Main Loop Per Akun ────────────────────────────────────────────────────
    def run(self):
        if self.startup_delay > 0:
            self.log.info(f"Startup delay {self.startup_delay:.1f}s...")
            time.sleep(self.startup_delay)

        self.log.info(f"=== Worker [{self.label}] dimulai ===")

        # Login awal
        login_ok = self._mis_login() and self._ethol_sso()
        when = timestamp_str()
        if login_ok:
            self.log.info(f"✅ Login ETHOL berhasil")
        else:
            self.log.warning(f"⚠️ Login awal gagal, akan re-auth berkala")

        # Kirim notif startup
        status_str = "✅ Login ETHOL berhasil, monitor aktif" if login_ok else "⚠️ Login awal gagal, akan re-auth berkala"
        send_wa(self.wa_target, (
            f"🚀 *Sistem Startup*\n\n"
            f"👤 *Akun:* {self.label}\n"
            f"⏰ *Waktu boot:* {when}\n"
            f"📌 *Status:* {status_str}\n\n"
            f"_Perangkat berhasil menyala dan terhubung ke internet._"
        ))

        # Loop utama
        refresh_counter = 0
        while True:
            try:
                if not in_window():
                    self.log.info("Di luar jadwal, istirahat 5 menit...")
                    time.sleep(300)
                    continue

                # Refresh token tiap ~10 menit (30 x 20 detik)
                refresh_counter += 1
                if refresh_counter >= 30:
                    try:
                        self.session.post(
                            "https://ethol.pens.ac.id/api/auth/refresh",
                            json={}, timeout=15
                        )
                    except Exception:
                        pass
                    refresh_counter = 0

                self._check_presensi()
                time.sleep(POLL_INTERVAL)

            except Exception as e:
                self.log.error(f"Error di main loop: {e}")
                time.sleep(30)


# ── Entry Point ───────────────────────────────────────────────────────────────
def main():
    if not ACCOUNTS:
        logging.error("ACCOUNTS_JSON kosong! Set environment variable ACCOUNTS_JSON.")
        return
    if not FONNTE_TOKEN:
        logging.warning("FONNTE_TOKEN kosong! Notifikasi WA tidak akan terkirim.")

    logging.info(f"=== ETHOL BOT MULTI-ACCOUNT | {len(ACCOUNTS)} akun ===")
    logging.info(f"Jadwal: Senin-Jumat jam {JAM_MULAI:02d}:00 - {JAM_SELESAI:02d}:00 WIB")
    logging.info(f"Poll interval: {POLL_INTERVAL} detik")

    threads = []
    for i, acc in enumerate(ACCOUNTS):
        delay = i * 5.0  # stagger 5 detik antar akun saat boot
        worker = AccountWorker(acc, startup_delay=delay)
        t = threading.Thread(target=worker.run, name=f"worker-{i}", daemon=True)
        t.start()
        threads.append(t)
        logging.info(f"Thread [{acc['user'].split('@')[0]}] dimulai (delay={delay}s)")

    # Jaga proses tetap hidup
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
