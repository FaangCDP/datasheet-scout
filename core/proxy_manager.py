"""
core/proxy_manager.py -- Proxy Pool Manager dengan Health Check & Fallback Otomatis.

Fitur:
1. Membaca daftar proxy dari file (default: proxies.txt atau path dari ENV).
2. Format didukung:
   - host:port
   - host:port:user:pass
   - http://user:pass@host:port
   - socks5://...
3. Mode fallback cerdas:
   - Jika file proxy kosong / tidak ada: fallback ke IP direct (ori server).
   - Jika proxy mati / 403 / timeout: otomatis beralih ke proxy berikutnya di daftar.
   - Menguji keaktifan proxy ke target URL (default: AllDatasheet).
"""

import os
import re
from curl_cffi import requests as cffi_requests


def parse_proxy_line(line: str) -> str | None:
    """Konversi format baris proxy teks menjadi URL standar http://..."""
    raw = line.strip()
    if not raw or raw.startswith("#"):
        return None

    # Jika sudah berformat URL lengkap (http://, https://, socks5://)
    if "://" in raw:
        return raw

    parts = raw.split(":")
    # Format: host:port
    if len(parts) == 2:
        host, port = parts
        return f"http://{host}:{port}"

    # Format: host:port:user:pass
    if len(parts) == 4:
        host, port, user, password = parts
        return f"http://{user}:{password}@{host}:{port}"

    return None


class ProxyManager:
    """Mengelola rotasi dan validasi pool proxy."""

    def __init__(self, proxy_file: str | None = None):
        self.proxy_file = proxy_file or os.getenv("PROXY_FILE", "proxies.txt")
        self.proxies: list[str] = []
        self._load_proxies()

    def _load_proxies(self):
        """Membaca seluruh proxy dari file teks."""
        self.proxies = []
        if not os.path.isfile(self.proxy_file):
            return

        try:
            with open(self.proxy_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    parsed = parse_proxy_line(line)
                    if parsed and parsed not in self.proxies:
                        self.proxies.append(parsed)
        except Exception as e:
            print(f"[ProxyManager WARNING] Gagal membaca {self.proxy_file}: {e}")

    def test_proxy(self, proxy_url: str, target_url: str = "https://www.alldatasheet.com/", timeout: int = 5) -> bool:
        """Menguji apakah proxy aktif dan berhasil menembus target URL (HTTP 200)."""
        try:
            r = cffi_requests.get(
                target_url,
                timeout=timeout,
                impersonate="chrome124",
                proxies={"http": proxy_url, "https": proxy_url}
            )
            return r.status_code == 200
        except Exception:
            return False

    def get_working_proxy(self, target_url: str = "https://www.alldatasheet.com/", timeout: int = 5) -> str | None:
        """
        Mencari proxy pertama yang aktif dari daftar.
        Jika tidak ada proxy yang aktif atau file kosong, mengembalikan None (fallback IP ori).
        """
        # Muat ulang jika ada pembaruan pada file teks
        self._load_proxies()

        if not self.proxies:
            return None

        print(f"[ProxyManager INFO] Menguji {len(self.proxies)} proxy pada '{self.proxy_file}'...")
        for idx, proxy in enumerate(self.proxies, 1):
            # Mask kredensial di log terminal
            masked = re.sub(r"://([^:@]+):([^@]+)@", r"://\1:****@", proxy)
            print(f" -> [{idx}/{len(self.proxies)}] Menguji proxy: {masked} ...", end=" ", flush=True)

            if self.test_proxy(proxy, target_url=target_url, timeout=timeout):
                print("🟢 AKTIF!")
                return proxy
            else:
                print("🔴 MATI / GAGAL (Lanjut ke proxy berikutnya...)")

        print("[ProxyManager WARNING] Seluruh proxy pada daftar tidak merespons. Fallback ke IP direct server.")
        return None
