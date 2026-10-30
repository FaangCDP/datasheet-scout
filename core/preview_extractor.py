"""
core/preview_extractor.py -- Modul Ekstraksi Thumbnail / Preview Halaman PDF

Modul terpisah dan mandiri untuk mengekstrak halaman pertama PDF menjadi gambar thumbnail PNG.
Tidak mengubah kode modul inti lain. Jika ekstraksi gagal, fungsi akan mengembalikan None
sehingga proses utama pengiriman dokumen PDF tidak akan terganggu.
"""

import os
import shutil
import subprocess

# Cek keberadaan binary pdftoppm di sistem
PDFTOPPM_BIN = shutil.which("pdftoppm")


def extract_pdf_thumbnail(pdf_path: str, max_width: int = 300) -> str | None:
    """
    Ekstrak halaman pertama (cover/pinout/diagram) dari file PDF menjadi gambar PNG thumbnail.

    Args:
        pdf_path: Path absolut atau relatif ke file PDF.
        max_width: Lebar maksimal gambar thumbnail dalam piksel (default: 300px).

    Returns:
        str: Path ke file thumbnail PNG jika berhasil.
        None: Jika ekstraksi gagal atau pdftoppm tidak tersedia.
    """
    if not PDFTOPPM_BIN:
        return None

    if not pdf_path or not os.path.isfile(pdf_path):
        return None

    try:
        pdf_dir = os.path.dirname(os.path.abspath(pdf_path))
        thumb_dir = os.path.join(pdf_dir, ".thumbnails")
        os.makedirs(thumb_dir, exist_ok=True)

        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        output_prefix = os.path.join(thumb_dir, f"{base_name}_thumb")
        expected_png = f"{output_prefix}-1.png"
        expected_png_alt = f"{output_prefix}-01.png"

        # Cek apakah thumbnail sudah pernah dibuat
        if os.path.isfile(expected_png) and os.path.getsize(expected_png) > 500:
            return expected_png
        if os.path.isfile(expected_png_alt) and os.path.getsize(expected_png_alt) > 500:
            return expected_png_alt

        # Jalankan pdftoppm untuk render halaman pertama (-f 1 -l 1)
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
        if result.returncode != 0:
            return None

        if os.path.isfile(expected_png):
            return expected_png
        if os.path.isfile(expected_png_alt):
            return expected_png_alt

        # Cek jika ada file keluaran lain dengan prefix yang sama
        for fname in os.listdir(thumb_dir):
            if fname.startswith(f"{base_name}_thumb") and fname.endswith(".png"):
                full_p = os.path.join(thumb_dir, fname)
                if os.path.getsize(full_p) > 500:
                    return full_p

        return None

    except Exception as e:
        print(f"[preview_extractor WARNING] Gagal mengekstrak thumbnail: {e}")
        return None
