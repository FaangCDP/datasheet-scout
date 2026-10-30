"""
sources/datasheet4u.py -- Sumber Database: datasheet4u.com

Modul khusus yang menangani konfigurasi HTTP, URL endpoint, dan logika scraping
spesifik untuk situs https://datasheet4u.com.
"""

import os
import random
import time
import requests
from bs4 import BeautifulSoup

NAME = "datasheet4u"
BASE_URL = "https://datasheet4u.com"

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
        full_url = f"{BASE_URL}{href}" if href.startswith("/") else href

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

    download_url = f"{BASE_URL}{download_href}" if download_href.startswith("/") else download_href
    human_delay(0.8, 1.8)

    # 2. Halaman unduh
    try:
        resp = session.get(download_url, timeout=30)
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

    pdf_url = f"{BASE_URL}{pdf_href}" if pdf_href.startswith("/") else pdf_href
    human_delay(0.8, 1.8)

    # 3. Stream & validasi berkas PDF
    try:
        resp = session.get(pdf_url, headers={"Referer": download_url}, timeout=120, stream=True)
        if resp.status_code != 200:
            return None

        chunks = resp.iter_content(chunk_size=65536)
        first_chunk = next(chunks, b"")
        if not first_chunk.startswith(b"%PDF-"):
            print(f"[{NAME} ERROR] Respons bukan file PDF valid (diduga halaman proteksi/HTML).")
            return None

        filename = sanitize_filename(part_no, manufacturer)
        file_path = os.path.join(download_folder, filename)

        with open(file_path, "wb") as f:
            f.write(first_chunk)
            for chunk in chunks:
                if chunk:
                    f.write(chunk)

        return file_path

    except (requests.RequestException, IOError) as e:
        print(f"[{NAME} ERROR] Gagal menyimpan PDF: {e}")
        return None
