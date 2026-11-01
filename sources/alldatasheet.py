"""
sources/alldatasheet.py -- Sumber Database: alldatasheet.com

Modul khusus yang menangani konfigurasi HTTP, URL endpoint, dan logika scraping
spesifik untuk situs https://www.alldatasheet.com.
Menggunakan curl_cffi untuk bypass Cloudflare TLS fingerprinting.
"""

import os
import random
import time
import urllib.parse
from bs4 import BeautifulSoup
from curl_cffi import requests

NAME = "alldatasheet"
BASE_URL = "https://www.alldatasheet.com"


def human_delay(min_s: float = 0.8, max_s: float = 2.0):
    """Delay acak sopan untuk menghindari pemblokiran rate limit."""
    time.sleep(random.uniform(min_s, max_s))


def create_session() -> requests.Session:
    """
    Buat session HTTP khusus alldatasheet.com dengan impersonasi browser
    dan ambil cookies proteksi Cloudflare (__cf_bm) dari homepage.
    Mendukung rotasi proxy bertingkat (proxies.txt -> IP ori).
    """
    # Gunakan impersonasi safari17_0 (terbukti lolos Cloudflare WAF pada jaringan proxy)
    session = requests.Session(impersonate="safari17_0")

    # 1. Cek proxy pool dari file proxies.txt / ENV
    active_proxy = None
    try:
        from core.proxy_manager import ProxyManager
        pm = ProxyManager()
        active_proxy = pm.get_working_proxy()
    except Exception as e:
        print(f"[{NAME} WARNING] Pemeriksaan proxy gagal: {e}")

    # Fallback ke ENV tunggal jika file kosong tapi ENV disetel
    if not active_proxy:
        single_env = os.getenv("ALLDATASHEET_PROXY", "").strip()
        if single_env:
            active_proxy = single_env

    if active_proxy:
        session.proxies = {"http": active_proxy, "https": active_proxy}
        print(f"[{NAME} INFO] Sesi AllDatasheet menggunakan proxy terverifikasi.")
    else:
        print(f"[{NAME} INFO] Sesi AllDatasheet menggunakan koneksi direct (IP asli server).")

    try:
        resp = session.get(BASE_URL + "/", timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"[{NAME} WARNING] Gagal mengakses homepage untuk cookies: {e}")
    return session


def sanitize_filename(part_no: str, manufacturer: str) -> str:
    """Sanitasi part number dan manufacturer untuk nama file PDF yang aman."""
    safe_part = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in part_no).strip('_')
    safe_mfr = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in manufacturer).strip().replace(' ', '_')
    return f"{safe_part}_{safe_mfr}_alldatasheet.pdf"


def search_component(session: requests.Session, component_name: str, needed: int = 5) -> list[dict]:
    """
    Cari komponen pada alldatasheet.com via /view.jsp?Searchword=...
    
    Returns:
        list of dict: [{"source": "alldatasheet", "part_no": ..., "manufacturer": ..., "url": ..., "href": ..., "description": ...}]
    """
    search_url = f"{BASE_URL}/view.jsp?Searchword={urllib.parse.quote(component_name)}"
    try:
        resp = session.get(search_url, timeout=30)
        if resp.status_code != 200:
            print(f"[{NAME} ERROR] HTTP status pencarian: {resp.status_code}")
            return []
    except Exception as e:
        print(f"[{NAME} ERROR] Gagal mencari '{component_name}': {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    links = soup.find_all("a", href=lambda h: h and "/datasheet-pdf/pdf/" in h)

    results = []
    seen = set()

    for a in links:
        if len(results) >= needed:
            break

        href = a.get("href", "")
        part_no = a.get_text(strip=True)
        if not part_no or href in seen:
            continue
        seen.add(href)

        # Temukan elemen parent row untuk mengekstrak pabrikan & deskripsi
        tr = a.find_parent("tr")
        manufacturer = "Unknown"
        description = ""

        if tr:
            img = tr.find("img")
            if img and img.get("alt"):
                manufacturer = img.get("alt").strip()
            tds = tr.find_all("td")
            for td in tds:
                txt = td.get_text(strip=True)
                if len(txt) > 5 and txt != part_no and txt != manufacturer:
                    description = txt
                    break

        full_url = "https:" + href if href.startswith("//") else href

        results.append({
            "source": NAME,
            "url": full_url,
            "href": href,
            "part_no": part_no,
            "manufacturer": manufacturer,
            "description": description,
        })

    return results


def download_single(session: requests.Session, result: dict, index: int = 1, download_folder: str = "downloads") -> str | None:
    """
    Unduh satu berkas datasheet PDF dari alldatasheet.com.
    Mengekstrak URL file PDF langsung melalui embed viewer pdf1.alldatasheet.com.
    
    Returns:
        str: path lengkap file yang disimpan jika sukses
        None: jika gagal
    """
    part_no = result.get("part_no", "Unknown")
    manufacturer = result.get("manufacturer", "Unknown")
    detail_url = result.get("url")

    if not detail_url:
        return None

    os.makedirs(download_folder, exist_ok=True)
    human_delay(0.8, 1.8)

    # 1. Navigasi ke halaman detail terlebih dahulu untuk membangun session cookies
    try:
        r_detail = session.get(detail_url, headers={"Referer": BASE_URL + "/"}, timeout=30)
        if r_detail.status_code != 200:
            print(f"[{NAME} ERROR] Gagal membuka detail page ({r_detail.status_code})")
            return None
    except Exception as e:
        print(f"[{NAME} ERROR] Request detail error: {e}")
        return None

    human_delay(0.5, 1.2)

    # 2. Buka halaman viewer pada domain yang sama (www.alldatasheet.com)
    # Contoh: https://www.alldatasheet.com/datasheet-pdf/pdf/17972/PHILIPS/NE555.html
    # -> https://www.alldatasheet.com/datasheet-pdf/view/17972/PHILIPS/NE555.html
    view_url = detail_url.replace(
        "/datasheet-pdf/pdf/",
        "/datasheet-pdf/view/"
    )

    try:
        r_view = session.get(view_url, headers={"Referer": detail_url}, timeout=30)
        if r_view.status_code != 200:
            # Fallback coba subdomain pdf1 jika www diblokir
            view_url_alt = detail_url.replace(
                "www.alldatasheet.com/datasheet-pdf/pdf/",
                "pdf1.alldatasheet.com/datasheet-pdf/view/"
            )
            r_view = session.get(view_url_alt, headers={"Referer": detail_url}, timeout=30)
            if r_view.status_code != 200:
                print(f"[{NAME} ERROR] Gagal membuka viewer ({r_view.status_code})")
                return None
            view_url = view_url_alt
    except Exception as e:
        print(f"[{NAME} ERROR] Request viewer error: {e}")
        return None

    soup = BeautifulSoup(r_view.text, "html.parser")

    # 2. Cari iframe viewer yang memuat parameter file PDF (pertahankan encoding token %2B)
    raw_viewer_url = None
    pdf_url = None

    for ifr in soup.find_all("iframe"):
        src = ifr.get("src", "")
        if "pdfjsview/web/viewer.html?file=" in src:
            raw_viewer_url = "https:" + src if src.startswith("//") else src
            raw_pdf_path = raw_viewer_url.split("file=")[1]
            pdf_url = "https:" + raw_pdf_path if raw_pdf_path.startswith("//") else raw_pdf_path
            break

    if not pdf_url:
        print(f"[{NAME} ERROR] Tautan PDF tidak ditemukan di halaman viewer")
        return None

    human_delay(0.8, 1.8)

    # 3. Unduh berkas PDF aktual dengan Referer viewer iframe
    try:
        r_pdf = session.get(pdf_url, headers={"Referer": raw_viewer_url}, timeout=60)
        if r_pdf.status_code != 200:
            print(f"[{NAME} ERROR] Gagal mengunduh PDF: HTTP {r_pdf.status_code}")
            return None

        if not r_pdf.content.startswith(b"%PDF-"):
            print(f"[{NAME} ERROR] Konten respons bukan PDF valid!")
            return None

        # Deteksi PDF dummy error (AllDatasheet mengirim PDF dummy 25.307 bytes saat hotlink dicegah)
        if len(r_pdf.content) == 25307:
            print(f"[{NAME} ERROR] Terdeteksi PDF dummy error AllDatasheet (website unavailable banner)!")
            return None

        # Validasi ukuran minimal dan penanda akhir %%EOF
        if len(r_pdf.content) < 2048:
            print(f"[{NAME} ERROR] Ukuran file PDF terlalu kecil ({len(r_pdf.content)} bytes).")
            return None

        if b"%%EOF" not in r_pdf.content[-1024:]:
            print(f"[{NAME} WARNING] Penanda %%EOF tidak ditemukan di akhir berkas (berkas mungkin terpotong).")

        filename = sanitize_filename(part_no, manufacturer)
        file_path = os.path.join(download_folder, filename)

        with open(file_path, "wb") as f:
            f.write(r_pdf.content)

        return file_path

    except Exception as e:
        print(f"[{NAME} ERROR] Gagal menyimpan file PDF: {e}")
        return None
