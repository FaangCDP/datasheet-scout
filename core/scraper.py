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

    if p_clean == q_clean:
        return 100.0
    if p_clean.startswith(q_clean):
        return 80.0
    if q_clean in p_clean:
        return 60.0

    q_words = [w for w in re.split(r"[^a-zA-Z0-9]", query.lower()) if w]
    p_words = [w for w in re.split(r"[^a-zA-Z0-9]", part.lower()) if w]
    overlap = set(q_words).intersection(set(p_words))
    if overlap:
        return 30.0 + 30.0 * (len(overlap) / len(q_words))
    for qw in q_words:
        if any(qw in pw for pw in p_words):
            return 20.0
    return 0.0


def search_component(session=None, component_name: str = "", needed: int = 1) -> list[dict]:
    """
    Cari komponen dengan mekanisme Relevance Ranking & Fallback Cerdas:
    1. Cari di datasheet4u.com dan ukur relevansi part number.
    2. Jika hasil kosong ATAU relevansi rendah (< 50, misal hanya cocok substring nama pabrikan),
       fallback otomatis ke alldatasheet.com.
    3. Urutkan hasil akhir berdasarkan skor relevansi tertinggi ke terendah.
    """
    comp_name = component_name.strip()
    if not comp_name:
        return []

    # 1. Coba sumber utama (datasheet4u)
    d4u_results = []
    try:
        s1 = session if session else datasheet4u.create_session()
        hits = datasheet4u.search_component(s1, comp_name, needed=max(needed, 5))
        if hits:
            for r in hits:
                r["source"] = "datasheet4u"
            d4u_results = hits
    except Exception as e:
        print(f"[datasheet4u search error]: {e}")

    # Cek apakah hasil datasheet4u relevan secara spesifik dengan part number
    max_d4u_score = max((compute_relevance(r, comp_name) for r in d4u_results), default=0.0)

    if d4u_results and max_d4u_score >= 50.0:
        d4u_results.sort(key=lambda r: compute_relevance(r, comp_name), reverse=True)
        return d4u_results[:needed]

    # 2. Fallback / Alternatif ke alldatasheet.com
    print(f"[AUTO-FALLBACK] '{comp_name}' (skor d4u: {max_d4u_score}), mencari di alldatasheet.com...")
    try:
        s2 = alldatasheet.create_session()
        all_hits = alldatasheet.search_component(s2, comp_name, needed=max(needed, 5))
        if all_hits:
            for r in all_hits:
                r["source"] = "alldatasheet"
            all_hits.sort(key=lambda r: compute_relevance(r, comp_name), reverse=True)
            max_all_score = compute_relevance(all_hits[0], comp_name)
            if max_all_score > max_d4u_score:
                return all_hits[:needed]
    except Exception as e:
        print(f"[alldatasheet fallback error]: {e}")

    # Jika alldatasheet juga tidak lebih baik, kembalikan d4u jika ada
    if d4u_results:
        d4u_results.sort(key=lambda r: compute_relevance(r, comp_name), reverse=True)
        return d4u_results[:needed]

    return []


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
