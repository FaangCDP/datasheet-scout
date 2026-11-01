"""
core/pinout_extractor.py -- Modul Deteksi & Ekstraksi Gambar Pinout dari PDF Datasheet

Mendukung pypdfium2 (Google PDFium Engine) sebagai mesin utama rendering tanpa butuh poppler OS.
Fallback otomatis ke pdftoppm / pdftotext jika tersedia.
"""

import os
import re
import shutil
import subprocess

try:
    import pypdfium2 as pdfium
    HAS_PYPDFIUM = True
except ImportError:
    HAS_PYPDFIUM = False

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
    if not pdf_path:
        return 1

    # METODE 1: pypdfium2 (Cari kata kunci teks langsung dari Python)
    if HAS_PYPDFIUM and os.path.isfile(pdf_path):
        try:
            pdf = pdfium.PdfDocument(pdf_path)
            total = len(pdf)
            scan_limit = min(total, max_pages)
            for page_idx in range(scan_limit):
                try:
                    text_page = pdf[page_idx].get_textpage()
                    txt = text_page.get_text_range()
                    for kw in PIN_KEYWORDS:
                        if re.search(kw, txt, re.I):
                            return page_idx + 1  # 1-indexed
                except Exception:
                    continue
            return 1
        except Exception:
            pass

    # METODE 2: pdftotext (Fallback jika poppler tersedia)
    if PDFTOTEXT_BIN:
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
    if not pdf_path or not os.path.isfile(pdf_path):
        return None, None

    try:
        pdf_dir = os.path.dirname(os.path.abspath(pdf_path))
        pinout_dir = os.path.join(pdf_dir, ".pinouts")
        os.makedirs(pinout_dir, exist_ok=True)

        page_num = find_pinout_page(pdf_path)
        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        output_png = os.path.join(pinout_dir, f"{base_name}_pinout_p{page_num}.png")

        if os.path.isfile(output_png) and os.path.getsize(output_png) > 1000:
            return output_png, page_num

        # METODE 1: pypdfium2 (Render gambar langsung via Google PDFium)
        if HAS_PYPDFIUM:
            try:
                pdf = pdfium.PdfDocument(pdf_path)
                page_idx = page_num - 1
                if 0 <= page_idx < len(pdf):
                    scale = resolution / 72.0  # Konversi DPI ke skala faktor PDFium
                    pil_img = pdf[page_idx].render(scale=scale).to_pil()
                    pil_img.save(output_png, format="PNG")
                    if os.path.isfile(output_png) and os.path.getsize(output_png) > 1000:
                        return output_png, page_num
            except Exception as e:
                print(f"[pinout_extractor WARNING] PDFium render pinout gagal: {e}")

        # METODE 2: pdftoppm (Fallback Linux CLI)
        if PDFTOPPM_BIN:
            output_prefix = os.path.join(pinout_dir, f"{base_name}_pinout_p{page_num}_ppm")
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
            if res.returncode == 0:
                for f in os.listdir(pinout_dir):
                    if f.startswith(f"{base_name}_pinout_p{page_num}_ppm") and f.endswith(".png"):
                        full = os.path.join(pinout_dir, f)
                        if os.path.getsize(full) > 1000:
                            return full, page_num

        return None, None

    except Exception as e:
        print(f"[pinout_extractor WARNING] Gagal mengekstrak diagram pinout: {e}")
        return None, None
