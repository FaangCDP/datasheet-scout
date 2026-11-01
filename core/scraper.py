"""
core/scraper.py -- Facade & Orchestrator Scraper Multi-Database

Menghubungkan aplikasi (CLI / Bot) dengan modul database sumber di folder sources/.
Mendukung failover/fallback otomatis: Jika komponen tidak ditemukan di datasheet4u,
pencarian secara otomatis dialihkan ke alldatasheet.com.
"""

from sources import datasheet4u, alldatasheet

SOURCES = {
    "datasheet4u": datasheet4u,
    "alldatasheet": alldatasheet,
}

BASE_URL = datasheet4u.BASE_URL
HEADERS = datasheet4u.HEADERS


def human_delay(min_s: float = 0.8, max_s: float = 2.0):
    datasheet4u.human_delay(min_s, max_s)


def format_duration(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}m {s}s" if m > 0 else f"{s}s"


def create_session():
    """Buat session default (datasheet4u)."""
    return datasheet4u.create_session()


def sanitize_filename(part_no: str, manufacturer: str, source: str = "datasheet4u") -> str:
    """Sanitasi nama file PDF berdasarkan provider sumber."""
    if source == "alldatasheet":
        return alldatasheet.sanitize_filename(part_no, manufacturer)
    return datasheet4u.sanitize_filename(part_no, manufacturer)


def compute_relevance(item: dict, query: str) -> float:
    """Hitung skor relevansi (0 - 100) antara part number hasil pencarian dengan kata kunci."""
    import re
    part = item.get("part_no", "")
    p_clean = re.sub(r"[^a-zA-Z0-9]", "", part).lower()
    q_clean = re.sub(r"[^a-zA-Z0-9]", "", query).lower()
    if not p_clean or not q_clean:
        return 0.0

    # 1. Exact match (identik sempurna, abaikan simbol)
    if p_clean == q_clean:
        return 100.0

    # 2. Cek apakah diawali query dan diikuti suffix kemasan/grade (misal: LM35DT, LM35DZ, LM35AH)
    # Jika query berakhir angka (seperti LM35), dan karakter berikutnya adalah HURUF (bukan angka),
    # itu adalah varian langsung LM35 (LM35D, LM35DZ, LM35CAZ, dll) -> relevansi sangat tinggi!
    # TAPI jika karakter berikutnya adalah ANGKA (misal LM358, LM350, LM3552),
    # itu adalah KOMPONEN YANG BERBEDA!
    if p_clean.startswith(q_clean):
        rest = p_clean[len(q_clean):]
        if q_clean[-1].isdigit() and rest and rest[0].isdigit():
            # Komponen berbeda! (misal LM35 -> LM358, LM350)
            return 40.0
        # Varian kemasan huruf (misal LM35 -> LM35D, LM35DZ)
        return 90.0

    # 3. Cek jika query ada di tengah tapi dipisahkan bukan angka
    if q_clean in p_clean:
        return 50.0

    q_words = [w for w in re.split(r"[^a-zA-Z0-9]", query.lower()) if w]
    p_words = [w for w in re.split(r"[^a-zA-Z0-9]", part.lower()) if w]
    overlap = set(q_words).intersection(set(p_words))
    if overlap:
        return 30.0 + 30.0 * (len(overlap) / len(q_words))
    for qw in q_words:
        if any(qw in pw for pw in p_words):
            return 20.0
    return 0.0


def search_component(session=None, component_name: str = "", needed: int = 15) -> list[dict]:
    """
    Cari komponen dengan mekanisme Relevance Ranking & Fallback Cerdas:
    1. Cari di datasheet4u.com dan ukur relevansi part number.
    2. Jika hasil d4u tidak memiliki exact/near-match (skor < 85), gabungkan atau fallback ke alldatasheet.com.
    3. Gabungkan dan urutkan hasil akhir berdasarkan skor relevansi tertinggi ke terendah.
    """
    comp_name = component_name.strip()
    if not comp_name:
        return []

    # Ambil pool kandidat yang lebih besar (minimal 25) agar paginasi katalog punya banyak pilihan
    pool_size = max(needed * 2, 25)

    d4u_results = []
    try:
        s1 = session if session else datasheet4u.create_session()
        hits = datasheet4u.search_component(s1, comp_name, needed=pool_size)
        if hits:
            for r in hits:
                r["source"] = "datasheet4u"
            d4u_results = hits
    except Exception as e:
        print(f"[datasheet4u search error]: {e}")

    # Cek apakah ada exact match (skor 100) di hasil d4u
    has_exact_d4u = any(compute_relevance(r, comp_name) == 100.0 for r in d4u_results)

    # Jika d4u TIDAK memiliki exact match (100) atau hasilnya kurang dari jumlah yang diminta,
    # hubungi alldatasheet.com untuk mengambil komponen exact match
    all_results = []
    if not has_exact_d4u or len(d4u_results) < needed:
        print(f"[AUTO-FALLBACK] '{comp_name}' (d4u tidak ada exact match 100), mencari di alldatasheet.com...")
        try:
            s2 = alldatasheet.create_session()
            all_hits = alldatasheet.search_component(s2, comp_name, needed=pool_size)
            if all_hits:
                for r in all_hits:
                    r["source"] = "alldatasheet"
                all_results = all_hits
        except Exception as e:
            print(f"[alldatasheet fallback error]: {e}")

    # Gabungkan kedua sumber dan lakukan deduplikasi berdasarkan URL / part_no + mfr
    combined = []
    seen = set()
    for item in (all_results + d4u_results if all_results else d4u_results):
        key = (item.get("part_no", "").upper(), item.get("manufacturer", "").upper())
        if key not in seen:
            seen.add(key)
            combined.append(item)

    # Urutkan berdasarkan skor relevansi:
    # 1. Exact match (LM35) -> skor 100
    # 2. Varian huruf/kemasan (LM35D, LM35DZ, LM35CA) -> skor 90
    # 3. Komponen lain (LM350, LM358) -> skor 40-50
    # Jika query berakhir angka, prioritaskan item yang part_no dasarnya benar-benar cocok!
    combined.sort(key=lambda r: compute_relevance(r, comp_name), reverse=True)
    return combined[:needed]


def download_single(session=None, result: dict = None, index: int = 1, download_folder: str = "downloads") -> str | None:
    """
    Unduh satu berkas datasheet PDF dengan mendelegasikan ke modul sumber yang sesuai
    (berdasarkan nilai result['source']).
    """
    if not result:
        return None

    source = result.get("source", "datasheet4u")
    if source == "alldatasheet":
        s = alldatasheet.create_session()
        return alldatasheet.download_single(s, result, index=index, download_folder=download_folder)
    else:
        s = session if session else datasheet4u.create_session()
        return datasheet4u.download_single(s, result, index=index, download_folder=download_folder)


def search_all_sources(component_name: str, needed: int = 3) -> list[dict]:
    """Cari komponen di seluruh database sumber secara bersamaan."""
    combined = []
    for name, module in SOURCES.items():
        try:
            s = module.create_session()
            hits = module.search_component(s, component_name, needed=needed)
            for h in hits:
                h["source"] = name
            combined.extend(hits)
        except Exception as e:
            print(f"[ERROR search_all_sources on {name}]: {e}")
    return combined
