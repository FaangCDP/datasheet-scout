"""
sources/datasheet4u.py -- Sumber Database: datasheet4u.com

Modul khusus yang menangani konfigurasi HTTP, URL endpoint, dan logika scraping
spesifik untuk situs https://datasheet4u.com.
"""

import os
import random
import time
import urllib.parse
import requests
from bs4 import BeautifulSoup

from core import pdf_fetch

NAME = "datasheet4u"
BASE_URL = "https://www.datasheet4u.com"

# Hanya URL https ke domain ini (atau subdomainnya) yang boleh di-request.
ALLOWED_HOSTS = ("datasheet4u.com",)


def is_allowed_url(url: str) -> bool:
    """True hanya untuk URL https ke domain sumber (cegah SSRF / URL absolut dari HTML)."""
    parsed = urllib.parse.urlparse(url or "")
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    return any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS)


# Konfigurasi Header Khusus datasheet4u.com:
# Hanya izinkan 'gzip, deflate'. Jangan sertakan 'br' (Brotli) karena
# server Cloudflare datasheet4u akan mengembalikan payload biner terkompresi
# yang tidak dapat didekompresi secara native oleh requests standar.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}


def human_delay(min_s: float = 0.8, max_s: float = 2.5):
    """Delay acak sopan untuk menghindari pemblokiran rate limit."""
    time.sleep(random.uniform(min_s, max_s))


def create_session() -> requests.Session:
    """Buat session HTTP khusus datasheet4u.com dengan cookies awal dari homepage."""
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        resp = session.get(BASE_URL, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[{NAME} WARNING] Gagal mengambil cookies homepage: {e}")
    return session


def sanitize_filename(part_no: str, manufacturer: str) -> str:
    """Sanitasi part number dan manufacturer untuk nama file PDF yang aman."""
    safe_part = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in part_no).strip('_')
    safe_mfr = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in manufacturer).strip().replace(' ', '_')
    return f"{safe_part}_{safe_mfr}_datasheet.pdf"


def search_component(session: requests.Session, component_name: str, needed: int = 5) -> list[dict]:
    """
    Cari komponen pada datasheet4u.com via /share_search.php.
    
    Returns:
        list of dict: [{"part_no": ..., "manufacturer": ..., "url": ..., "href": ..., "description": ...}]
    """
    search_url = f"{BASE_URL}/share_search.php"
    try:
        resp = session.get(search_url, params={"sWord": component_name}, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[{NAME} ERROR] Gagal mencari '{component_name}': {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.select_one("table.search-results")
    if not table:
        return []

    results = []
    links = table.select("a.line")

    for link in links:
        if len(results) >= needed:
            break

        href = link.get("href", "")
        part_no = link.get_text(strip=True)
        row = link.find_parent("tr")
        if not row:
            continue

        mfr_span = row.select_one("span.mfr-name")
        manufacturer = mfr_span.get_text(strip=True) if mfr_span else "Unknown"

        tds = row.select("td")
        description = tds[-1].get_text(strip=True) if len(tds) >= 3 else ""
        full_url = urllib.parse.urljoin(BASE_URL, href)
        if not is_allowed_url(full_url):
            print(f"[{NAME} WARNING] Tautan hasil pencarian ditolak (host di luar allowlist).")
            continue

        if any(r["href"] == href for r in results):
            continue

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
    Unduh satu berkas datasheet PDF dari datasheet4u.com.
    
    Returns:
        str: path lengkap file yang disimpan jika sukses
        None: jika gagal
    """
    part_no = result.get("part_no", "Unknown")
    manufacturer = result.get("manufacturer", "Unknown")
    detail_url = result.get("url")

    if not detail_url:
        return None

    if not is_allowed_url(detail_url):
        print(f"[{NAME} ERROR] URL detail ditolak (host di luar allowlist).")
        return None

    os.makedirs(download_folder, exist_ok=True)
    human_delay(0.8, 1.8)

    # 1. Halaman detail
    try:
        resp = session.get(detail_url, timeout=30)
        if resp.status_code != 200:
            return None
    except requests.RequestException:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    download_href = None
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if "/download/" in href and href.endswith(".html"):
            download_href = href
            break

    if not download_href:
        return None

    download_url = urllib.parse.urljoin(BASE_URL, download_href)
    if not is_allowed_url(download_url):
        print(f"[{NAME} ERROR] URL unduhan ditolak (host di luar allowlist).")
        return None
    human_delay(0.8, 1.8)

    # 2. Halaman unduh
    try:
        resp = session.get(download_url, timeout=30, allow_redirects=False)
        # Handle redirects manual untuk cegah SSRF bypass via redirect
        redirects = 0
        while resp.status_code in (301, 302, 303, 307, 308) and redirects < 5:
            location = resp.headers.get("Location")
            if not location:
                break
            next_url = urllib.parse.urljoin(download_url, location)
            if not is_allowed_url(next_url):
                print(f"[{NAME} ERROR] Redirect ke host luar allowlist, dihentikan.")
                return None
            resp = session.get(next_url, timeout=30, allow_redirects=False)
            download_url = next_url
            redirects += 1
        if resp.status_code != 200:
            return None
    except requests.RequestException:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    pdf_href = None

    for a in soup.select("a[href]"):
        text = a.get_text(strip=True)
        href = a.get("href", "")
        if "Download" in text and "Datasheet PDF" in text and ".pdf" in href:
            pdf_href = href
            break

    if not pdf_href:
        for a in soup.select("a[href$='.pdf']"):
            pdf_href = a.get("href", "")
            break

    if not pdf_href:
        iframe = soup.select_one("iframe[src$='.pdf']")
        if iframe:
            pdf_href = iframe.get("src", "")

    if not pdf_href:
        return None

    pdf_url = urllib.parse.urljoin(BASE_URL, pdf_href)
    if not is_allowed_url(pdf_url):
        print(f"[{NAME} ERROR] URL PDF ditolak (host di luar allowlist).")
        return None
    human_delay(0.8, 1.8)

    # 3. Stream & validasi berkas PDF (batas ukuran untuk mencegah penuhnya disk)
    # Redirect manual + tutup koneksi stream selalu (S-01, T-01)
    resp = None
    try:
        resp = session.get(pdf_url, headers={"Referer": download_url}, timeout=120,
                            stream=True, allow_redirects=False)
        # Redirect ke host di luar allowlist harus ditolak (T-01)
        redirects = 0
        while resp.status_code in (301, 302, 303, 307, 308) and redirects < 5:
            location = resp.headers.get("Location")
            if not location:
                break
            next_url = urllib.parse.urljoin(pdf_url, location)
            if not is_allowed_url(next_url):
                print(f"[{NAME} ERROR] Redirect ke host luar allowlist, dihentikan.")
                return None
            resp = session.get(next_url, headers={"Referer": download_url}, timeout=120,
                                stream=True, allow_redirects=False)
            pdf_url = next_url
            redirects += 1
        if resp.status_code != 200:
            return None

        if pdf_fetch.content_length_exceeds(resp):
            print(f"[{NAME} ERROR] PDF melebihi batas {pdf_fetch.MAX_PDF_BYTES // (1024 * 1024)} MB, unduhan dibatalkan.")
            return None

        chunks = resp.iter_content(chunk_size=65536)
        first_chunk = next(chunks, b"")
        if not first_chunk.startswith(b"%PDF-"):
            print(f"[{NAME} ERROR] Respons bukan file PDF valid (diduga halaman proteksi/HTML).")
            return None

        filename = sanitize_filename(part_no, manufacturer)
        file_path = os.path.join(download_folder, filename)

        file_sz = pdf_fetch.write_capped(chunks, file_path, initial=first_chunk)
        if file_sz is None:
            print(f"[{NAME} ERROR] Berkas melebihi batas {pdf_fetch.MAX_PDF_BYTES // (1024 * 1024)} MB, unduhan dibatalkan.")
            return None

        # Validasi kelengkapan berkas: minimal 2KB dan pengecekan trailer %%EOF
        if file_sz < pdf_fetch.MIN_PDF_BYTES:
            print(f"[{NAME} ERROR] Ukuran berkas PDF terlalu kecil ({file_sz} bytes), diduga rusak.")
            try:
                os.remove(file_path)
            except OSError:
                pass

            return None

        with open(file_path, "rb") as f:
            f.seek(max(0, file_sz - 1024))
            tail = f.read()
        if b"%%EOF" not in tail:
            print(f"[{NAME} ERROR] Penanda %%EOF tidak ditemukan (PDF terpotong), file dihapus.")
            try:
                os.remove(file_path)
            except OSError:
                pass
            return None

        return file_path

    except (requests.RequestException, IOError) as e:
        print(f"[{NAME} ERROR] Gagal menyimpan PDF: {e}")
        return None
    finally:
        # S-01: pastikan koneksi stream selalu ditutup
        if resp is not None:
            resp.close()
