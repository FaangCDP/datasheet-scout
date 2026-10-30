"""
core/pinout_extractor.py -- Modul Deteksi & Ekstraksi Gambar Pinout dari PDF Datasheet

Modul mandiri yang mencari halaman konfigurasi/diagram kaki (pinout) pada dokumen PDF
dan merendernya menjadi gambar PNG resolusi tinggi.
Jika proses gagal, modul akan mengembalikan (None, None) tanpa mengganggu alur sistem.
"""

import os
import re
import shutil
import subprocess

PDFTOTEXT_BIN = shutil.which("pdftotext")
PDFTOPPM_BIN = shutil.which("pdftoppm")
PDFINFO_BIN = shutil.which("pdfinfo")

PIN_KEYWORDS = [
    r"\bpin\s*(?:configurations?|layouts?|assignments?|descriptions?|diagrams?|connections?)\b",
    r"\bconnection\s*diagrams?\b",
    r"\bpinout\b",
    r"\bterminal\s*(?:functions?|assignments?)\b",
]


def find_pinout_page(pdf_path: str, max_pages: int = 15) -> int:
    """
    Pindai halaman PDF untuk menemukan nomor halaman diagram susunan kaki/pinout.
    """
    if not PDFTOTEXT_BIN:
        return 1

    total_pages = 1
    if PDFINFO_BIN:
        try:
            info = subprocess.run(
                [PDFINFO_BIN, pdf_path],
                capture_output=True,
                text=True,
                errors="ignore",
                timeout=5,
            ).stdout
            m = re.search(r"Pages:\s+(\d+)", info)
            if m:
                total_pages = int(m.group(1))
        except Exception:
            pass

    scan_limit = min(total_pages, max_pages)

    for page_num in range(1, scan_limit + 1):
        try:
            txt = subprocess.run(
                [PDFTOTEXT_BIN, "-f", str(page_num), "-l", str(page_num), pdf_path, "-"],
                capture_output=True,
                text=True,
                errors="ignore",
                timeout=5,
            ).stdout

            for kw in PIN_KEYWORDS:
                if re.search(kw, txt, re.I):
                    return page_num
        except Exception:
            continue

    return 1


def extract_pinout_image(pdf_path: str, resolution: int = 150) -> tuple[str | None, int | None]:
    """
    Render halaman pinout dari file PDF menjadi file gambar PNG.

    Args:
        pdf_path: Path file PDF di disk.
        resolution: Resolusi render DPI (default: 150 DPI untuk ketajaman diagram).

    Returns:
        tuple (path_gambar_png, nomor_halaman) jika berhasil, atau (None, None) jika gagal.
    """
    if not PDFTOPPM_BIN or not pdf_path or not os.path.isfile(pdf_path):
        return None, None

    try:
        pdf_dir = os.path.dirname(os.path.abspath(pdf_path))
        pinout_dir = os.path.join(pdf_dir, ".pinouts")
        os.makedirs(pinout_dir, exist_ok=True)

        page_num = find_pinout_page(pdf_path)
        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        output_prefix = os.path.join(pinout_dir, f"{base_name}_pinout_p{page_num}")

        expected_1 = f"{output_prefix}-{page_num:02d}.png"
        expected_2 = f"{output_prefix}-{page_num}.png"
        expected_3 = f"{output_prefix}-1.png"

        # Cek jika gambar pinout halaman tersebut sudah pernah di-render
        for exp in (expected_1, expected_2, expected_3):
            if os.path.isfile(exp) and os.path.getsize(exp) > 1000:
                return exp, page_num

        cmd = [
            PDFTOPPM_BIN,
            "-png",
            "-f", str(page_num),
            "-l", str(page_num),
            "-r", str(resolution),
            pdf_path,
            output_prefix,
        ]

        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        if res.returncode != 0:
            return None, None

        for exp in (expected_1, expected_2, expected_3):
            if os.path.isfile(exp) and os.path.getsize(exp) > 1000:
                return exp, page_num

        # Cek jika ada file keluaran lain dengan prefix tersebut
        for f in os.listdir(pinout_dir):
            if f.startswith(f"{base_name}_pinout_p{page_num}") and f.endswith(".png"):
                full = os.path.join(pinout_dir, f)
                if os.path.getsize(full) > 1000:
                    return full, page_num

        return None, None

    except Exception as e:
        print(f"[pinout_extractor WARNING] Gagal mengekstrak diagram pinout: {e}")
        return None, None
