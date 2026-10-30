"""
core/package_classifier.py -- Modul Deteksi & Klasifikasi Kemasan Fisik IC/Komponen

Modul terpisah untuk memangkas suffix nama komponen dan mengelompokkan
hasil pencarian ke dalam kemasan fisik (package) yang berbeda-beda.
"""

import re

# Aturan konvensi suffix manufaktur (TI, ST, ON Semi, NXP, Microchip, ROHM)
SUFFIX_PKG_RULES = [
    (r"(?:[NP]|_N|-N|PDIP)\b", "DIP"),
    (r"(?:[D]|DT|DR|SO|SOIC|SOP)\b", "SOIC"),
    (r"(?:PW|PWR|TSSOP|PT|APT)\b", "TSSOP"),
    (r"(?:MSOP|DGK|FVM|FVT)\b", "MSOP"),
    (r"(?:SOT|DBV|DCK)\b", "SOT-23"),
    (r"(?:QFN|RTE|QT)\b", "QFN"),
    (r"(?:TO-?99|H)\b", "TO-99"),
    (r"(?:TO-?92)\b", "TO-92"),
    (r"(?:TO-?220)\b", "TO-220"),
    (r"(?:TQFP|LQFP)\b", "TQFP"),
]

EXPLICIT_KEYWORDS = [
    ("PDIP", "DIP"),
    ("DIP", "DIP"),
    ("SOIC", "SOIC"),
    ("SOP", "SOIC"),
    ("TSSOP", "TSSOP"),
    ("MSOP", "MSOP"),
    ("SOT-23", "SOT-23"),
    ("SOT-223", "SOT-223"),
    ("TO-92", "TO-92"),
    ("TO-220", "TO-220"),
    ("TO-126", "TO-126"),
    ("QFN", "QFN"),
    ("DFN", "DFN"),
    ("TQFP", "TQFP"),
    ("LQFP", "TQFP"),
]


def clean_base_component(comp_name: str) -> str:
    """
    Ekstrak nama dasar komponen dengan memangkas suffix kemasan/grade.
    Contoh: LM358D -> LM358, NE555P -> NE555, LM358-N -> LM358, ATMEGA328P-PU -> ATMEGA328P.
    """
    c = comp_name.strip()

    # Pangkas suffix dash umum seperti -PU, -AU, -N, -D
    c_sub = re.sub(r"[-_/]([A-Za-z0-9]{1,3})$", "", c)
    if len(c_sub) >= 3 and any(char.isdigit() for char in c_sub):
        c = c_sub

    # Pangkas suffix huruf tunggal/ganda kemasan di belakang angka part
    m = re.match(r"^([A-Za-z]{1,4}\d{2,5}[A-Za-z]?)(?:[DNPST]|DR|DT|QT|PT)$", c, re.I)
    if m:
        c = m.group(1)

    return c


def detect_package_from_item(item: dict) -> str | None:
    """
    Deteksi tipe kemasan fisik (package) dari part number dan deskripsi komponen.
    """
    part = item.get("part_no", "").upper()
    desc = item.get("description", "").upper()
    full_text = f"{part} {desc}"

    # 1. Cek kata kunci eksplisit
    for kw, label in EXPLICIT_KEYWORDS:
        if re.search(r"\b" + kw + r"\b", full_text):
            return label

    # 2. Cek pola akhiran part number
    for pat, label in SUFFIX_PKG_RULES:
        if re.search(pat, part):
            return label

    return None


def select_distinct_packages(candidates: list[dict], max_items: int = 5) -> dict[str, dict]:
    """
    Pilih hingga max_items varian dengan kemasan fisik yang saling berbeda.

    Returns:
        dict: { "DIP": item_dict, "SOIC": item_dict, ... }
    """
    distinct = {}
    for item in candidates:
        pkg = detect_package_from_item(item)
        if pkg and pkg not in distinct:
            distinct[pkg] = item
            if len(distinct) >= max_items:
                break
    return distinct
