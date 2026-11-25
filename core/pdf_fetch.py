"""
core/pdf_fetch.py -- Batas ukuran aman untuk PDF pihak ketiga.

Semua PDF berasal dari situs eksternal (atau proxy yang tidak dipercaya), jadi
ukuran body wajib dibatasi sebelum masuk RAM, disk, atau parser PDF.
Batas diatur via ENV: MAX_PDF_SIZE_MB (unduhan, default 30), MAX_PARSE_SIZE_MB (parsing, default 40).
"""

import os

from core.env_utils import parse_int_env

MAX_PDF_BYTES = parse_int_env("MAX_PDF_SIZE_MB", 30, min_value=1) * 1024 * 1024
MAX_PARSE_BYTES = parse_int_env("MAX_PARSE_SIZE_MB", 40, min_value=1) * 1024 * 1024
MIN_PDF_BYTES = 2048


def content_length_exceeds(resp, limit: int = MAX_PDF_BYTES) -> bool:
    """True jika header Content-Length sudah menyatakan body lebih besar dari batas."""
    headers = getattr(resp, "headers", None) or {}
    raw = str(headers.get("Content-Length", "") or "").strip()
    return raw.isdigit() and int(raw) > limit


def read_capped(resp, limit: int = MAX_PDF_BYTES, chunk_size: int = 65536) -> bytes | None:
    """Baca body respons sampai batas byte. None jika kosong atau melebihi batas."""
    total = 0
    chunks = []
    for chunk in resp.iter_content(chunk_size=chunk_size):
        if not chunk:
            continue
        total += len(chunk)
        if total > limit:
            return None
        chunks.append(chunk)
    return b"".join(chunks) or None


def write_capped(chunks, file_path: str, initial: bytes = b"", limit: int = MAX_PDF_BYTES) -> int | None:
    """Tulis `initial` + sisa chunk ke file dengan batas byte.

    Returns:
        int: total byte yang tertulis.
        None: jika melebihi batas (file yang sudah ditulis dihapus kembali).
    """
    total = len(initial)
    exceeded = total > limit
    with open(file_path, "wb") as f:
        if not exceeded:
            f.write(initial)
            for chunk in chunks:
                if not chunk:
                    continue
                total += len(chunk)
                if total > limit:
                    exceeded = True
                    break
                f.write(chunk)
    if exceeded:
        try:
            os.remove(file_path)
        except OSError:
            pass
        return None
    return total


def too_large_to_parse(pdf_path: str, limit: int = MAX_PARSE_BYTES) -> bool:
    """True jika file tidak ada atau melebihi batas ukuran untuk diparse."""
    try:
        return os.path.getsize(pdf_path) > limit
    except OSError:
        return True
