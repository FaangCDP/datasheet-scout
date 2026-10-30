"""
core/specs_extractor.py -- Modul Ekstraksi Spesifikasi Kunci Komponen dari PDF

Modul terpisah dan mandiri untuk membaca halaman awal PDF datasheet
dan mengekstrak spesifikasi kunci (Tegangan kerja, Frekuensi/Clock, Kemasan, Suhu operasi).
Jika pdftotext tidak tersedia atau ekstraksi tidak menemukan parameter, fungsi akan
mengembalikan dictionary kosong tanpa mengganggu alur utama pengunduhan PDF.
"""

import os
import re
import shutil
import subprocess

PDFTOTEXT_BIN = shutil.which("pdftotext")


def extract_key_specs(pdf_path: str, max_pages: int = 3) -> dict[str, str]:
    """
    Ekstrak ringkasan spesifikasi kunci dari dokumen datasheet PDF.

    Args:
        pdf_path: Path ke file PDF di disk.
        max_pages: Jumlah halaman awal yang dipindai (default: 3 halaman).

    Returns:
        dict: Pasangan {"Nama Parameter": "Nilai Parameter"} yang berhasil diekstrak.
    """
    if not PDFTOTEXT_BIN:
        return {}

    if not pdf_path or not os.path.isfile(pdf_path):
        return {}

    try:
        cmd = [PDFTOTEXT_BIN, "-f", "1", "-l", str(max_pages), pdf_path, "-"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            errors="ignore",
            timeout=10,
        )

        text = result.stdout
        if not text:
            return {}

        specs = {}

        # 1. Tegangan Kerja / Supply Voltage
        # Contoh: "3V to 36V", "2.0V-5.5V", "Supply Voltage: 5V"
        v_match = re.search(
            r"(?:supply\s*(?:voltage|range)?|operating\s*(?:voltage|range)?)[^\n\r:]{0,30}[:\s]\s*([0-9]+(?:\.[0-9]+)?\s*V\s*(?:to|-)\s*[0-9]+(?:\.[0-9]+)?\s*V)",
            text,
            re.I,
        )
        if not v_match:
            v_match = re.search(
                r"\b([0-9]+(?:\.[0-9]+)?\s*V\s*(?:to|-)\s*[0-9]+(?:\.[0-9]+)?\s*V)\s*(?:supply|operating)?",
                text,
                re.I,
            )
        if not v_match:
            v_single = re.search(
                r"(?:operating\s+voltage|supply\s+voltage)[^\n\r:]{0,25}[:\s]\s*([0-9]+(?:\.[0-9]+)?\s*V)\b",
                text,
                re.I,
            )
            if v_single:
                specs["Tegangan Kerja"] = v_single.group(1).strip()
        else:
            specs["Tegangan Kerja"] = v_match.group(1).strip()

        # 2. Frekuensi / Clock Speed
        # Contoh: "16 MHz", "20 MHz", "2.4 GHz", "500kHz"
        freq_match = re.search(
            r"(\b[0-9]+(?:\.[0-9]+)?\s*(?:MHz|GHz|kHz))\s*(?:crystal|oscillator|clock|frequency|CPU|combo|Wi-Fi)",
            text,
            re.I,
        )
        if not freq_match:
            freq_match = re.search(
                r"(?:frequency|clock\s+speed)[^\n\r:]{0,25}[:\s]\s*([0-9]+(?:\.[0-9]+)?\s*(?:MHz|GHz|kHz))\b",
                text,
                re.I,
            )
        if freq_match:
            specs["Frekuensi/Clock"] = freq_match.group(1).strip()

        # 3. Tipe Kemasan / Package
        # Contoh: DIP-8, SOIC, TSSOP, TO-220, TQFP
        pkgs = re.findall(
            r"\b(DIP-?\d*|SOIC-?\d*|SOP-?\d*|TSSOP-?\d*|MSOP-?\d*|TQFP-?\d*|LQFP-?\d*|QFN-?\d*|TO-220|TO-92|SOT-23-?\d*)\b",
            text,
            re.I,
        )
        if pkgs:
            clean_pkgs = []
            for p in pkgs:
                p_up = p.upper().strip()
                if p_up not in clean_pkgs and len(p_up) >= 3:
                    clean_pkgs.append(p_up)
            if clean_pkgs:
                specs["Kemasan/Package"] = ", ".join(clean_pkgs[:4])

        # 4. Rentang Suhu Operasi
        # Contoh: "-40°C to +85°C", "0°C to 70°C"
        temp_match = re.search(r"(-?[0-9]+\s*°?C\s*(?:to|-)\s*\+?[0-9]+\s*°?C)", text, re.I)
        if temp_match:
            specs["Suhu Operasi"] = temp_match.group(1).strip()

        return specs

    except Exception as e:
        print(f"[specs_extractor WARNING] Gagal mengekstrak spesifikasi: {e}")
        return {}
