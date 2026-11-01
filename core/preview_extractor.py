"""
core/preview_extractor.py -- Modul Ekstraksi Thumbnail / Preview Halaman PDF

Mendukung dua mesin rendering:
1. pypdfium2 (Google PDFium Python Engine) - Mandiri, tidak butuh poppler OS (Cocok untuk Pterodactyl/VPS).
2. pdftoppm (Poppler CLI) - Fallback native Linux jika tersedia.
"""

import os
import shutil
import subprocess

# Cek ketersediaan pypdfium2 (prioritas utama untuk environment hosting container)
try:
    import pypdfium2 as pdfium
    HAS_PYPDFIUM = True
except ImportError:
    HAS_PYPDFIUM = False

# Cek keberadaan binary pdftoppm di sistem OS
PDFTOPPM_BIN = shutil.which("pdftoppm")


def extract_pdf_thumbnail(pdf_path: str, max_width: int = 300) -> str | None:
    """
    Ekstrak halaman pertama (cover/pinout/diagram) dari file PDF menjadi gambar PNG thumbnail.

    Args:
        pdf_path: Path absolut atau relatif ke file PDF.
        max_width: Lebar maksimal gambar thumbnail dalam piksel (default: 300px).

    Returns:
        str: Path ke file thumbnail PNG jika berhasil.
        None: Jika ekstraksi gagal.
    """
    if not pdf_path or not os.path.isfile(pdf_path):
        return None

    try:
        pdf_dir = os.path.dirname(os.path.abspath(pdf_path))
        thumb_dir = os.path.join(pdf_dir, ".thumbnails")
        os.makedirs(thumb_dir, exist_ok=True)

        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        output_png = os.path.join(thumb_dir, f"{base_name}_thumb.png")

        if os.path.isfile(output_png) and os.path.getsize(output_png) > 500:
            return output_png

        # METODE 1: pypdfium2 (Python engine mandiri)
        if HAS_PYPDFIUM:
            try:
                pdf = pdfium.PdfDocument(pdf_path)
                if len(pdf) > 0:
                    page = pdf[0]
                    # Hitung rasio skala agar lebar maksimal sesuai
                    page_width = page.get_width()
                    scale = (max_width / page_width) if page_width > 0 else 1.0
                    pil_image = page.render(scale=scale).to_pil()
                    pil_image.save(output_png, format="PNG")
                    if os.path.isfile(output_png) and os.path.getsize(output_png) > 500:
                        return output_png
            except Exception as e:
                print(f"[preview_extractor WARNING] PDFium render gagal, mencoba pdftoppm: {e}")

        # METODE 2: pdftoppm (Fallback Linux CLI)
        if PDFTOPPM_BIN:
            output_prefix = os.path.join(thumb_dir, f"{base_name}_thumb_ppm")
            cmd = [
                PDFTOPPM_BIN,
                "-png",
                "-f", "1",
                "-l", "1",
                "-scale-to", str(max_width),
                pdf_path,
                output_prefix,
            ]
            result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            if result.returncode == 0:
                for fname in os.listdir(thumb_dir):
                    if fname.startswith(f"{base_name}_thumb_ppm") and fname.endswith(".png"):
                        full_p = os.path.join(thumb_dir, fname)
                        if os.path.getsize(full_p) > 500:
                            return full_p

        return None

    except Exception as e:
        print(f"[preview_extractor WARNING] Gagal mengekstrak thumbnail: {e}")
        return None
