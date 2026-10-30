"""
batch_download_http.py -- Batch Datasheet Downloader (HTTP Mode)

Versi ringan tanpa Playwright. Menggunakan requests + BeautifulSoup.
Membaca file .txt dari folder 'list/', setiap file = 1 kategori komponen.

Dependensi:
  pip install requests beautifulsoup4

Cara pakai:
  python batch_download_http.py
"""

import os
import sys
import time
import argparse

# Import fungsi dari core scraper
from core.scraper import (
    BASE_URL,
    human_delay,
    format_duration,
    create_session,
    search_component,
    download_single,
    sanitize_filename,
)


# ================================================================
# FUNGSI PEMBACA LIST
# ================================================================

def scan_list_folder(list_folder: str) -> list[dict]:
    """
    Scan folder 'list/' dan baca semua file .txt.
    Setiap file = 1 kategori. Nama file (tanpa .txt) = nama kategori.
    """
    list_folder = os.path.abspath(list_folder)

    if not os.path.isdir(list_folder):
        print(f"[ERROR] Folder '{list_folder}' tidak ditemukan!")
        print(f"        Buat folder 'list/' dan isi dengan file .txt.")
        return []

    categories = []

    for filename in sorted(os.listdir(list_folder)):
        if not filename.lower().endswith(".txt"):
            continue

        file_path = os.path.join(list_folder, filename)
        category_name = os.path.splitext(filename)[0]

        components = read_component_file(file_path)

        if len(components) == 0:
            print(f"    [!] {filename} -- kosong, dilewati.")
            continue

        categories.append({
            "category": category_name,
            "file_path": file_path,
            "components": components
        })

    return categories


def read_component_file(file_path: str) -> list[str]:
    """
    Baca file .txt dan kembalikan list nama komponen yang bersih.
    - Abaikan baris kosong dan komentar (#)
    - Hilangkan duplikat (pertahankan urutan)
    """
    components = []
    seen = set()

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                name = line.strip()
                if not name or name.startswith("#"):
                    continue
                name_upper = name.upper()
                if name_upper in seen:
                    continue
                seen.add(name_upper)
                components.append(name)

    except UnicodeDecodeError:
        try:
            with open(file_path, "r", encoding="latin-1") as f:
                for line in f:
                    name = line.strip()
                    if not name or name.startswith("#"):
                        continue
                    name_upper = name.upper()
                    if name_upper not in seen:
                        seen.add(name_upper)
                        components.append(name)
        except Exception as e:
            print(f"[ERROR] Gagal membaca file {file_path}: {e}")

    except FileNotFoundError:
        print(f"[ERROR] File tidak ditemukan: {file_path}")

    return components


# ================================================================
# FUNGSI SEARCH & DOWNLOAD PER KOMPONEN
# ================================================================

def search_and_download(session, component_name: str, count: int, download_folder: str) -> dict:
    """
    Cari komponen dan download datasheet via HTTP session bersama.

    Returns:
        dict: {component, requested, success, fail, skipped_reason, elapsed}
    """
    comp_start = time.time()

    result_summary = {
        "component": component_name,
        "requested": count,
        "success": 0,
        "fail": 0,
        "skipped_reason": None,
        "elapsed": 0.0,
    }

    # --- Cari komponen ---
    if "br" in session.headers.get("Accept-Encoding", ""):
        session.headers["Accept-Encoding"] = "gzip, deflate"
    human_delay(0.8, 2.0)
    results = search_component(session, component_name, needed=count)

    if not results:
        print(f"    [!] Tidak ada hasil untuk '{component_name}'. Dilewati.")
        result_summary["skipped_reason"] = "Tidak ada hasil pencarian"
        result_summary["elapsed"] = time.time() - comp_start
        return result_summary

    if len(results) < count:
        print(f"    [!] Hanya ditemukan {len(results)} dari {count} yang diminta.")
    else:
        print(f"    [+] Ditemukan {len(results)} hasil, mulai download...")

    # --- Download loop ---
    for i, res in enumerate(results, 1):
        # Skip existing: cek apakah file sudah ada di folder tujuan
        filename = sanitize_filename(res["part_no"], res["manufacturer"])
        expected_file = os.path.join(download_folder, filename)
        if os.path.isfile(expected_file) and os.path.getsize(expected_file) > 1000:
            print(f"    [SKIP] {res['part_no']} sudah ada ({os.path.getsize(expected_file)} bytes)")
            result_summary["success"] += 1
            continue

        ok = download_single(session, res, i, download_folder)
        if ok:
            result_summary["success"] += 1
        else:
            result_summary["fail"] += 1

        if i < len(results):
            human_delay(2.0, 4.0)

    result_summary["elapsed"] = time.time() - comp_start
    print(f"    [i] Waktu untuk {component_name}: {format_duration(result_summary['elapsed'])}")
    return result_summary


# ================================================================
# FUNGSI UTAMA BATCH
# ================================================================

def batch_download(count_per_component: int, list_folder: str = "list", output_folder: str = "downloads", auto_confirm: bool = False):
    """Proses batch: baca semua kategori dari folder list, download datasheet."""

    print(f"\n{'#'*60}")
    print(f"  BATCH DATASHEET DOWNLOADER (HTTP Mode)")
    print(f"  Jumlah per komponen : {count_per_component}")
    print(f"  Folder list         : {os.path.abspath(list_folder)}")
    print(f"  Folder output       : {os.path.abspath(output_folder)}")
    print(f"{'#'*60}")

    # --- Scan folder list ---
    print(f"\n[+] Scanning folder '{list_folder}'...")
    categories = scan_list_folder(list_folder)

    if len(categories) == 0:
        print("[ERROR] Tidak ada file .txt yang valid di folder list.")
        return

    # --- Tampilkan ringkasan ---
    total_components = sum(len(cat["components"]) for cat in categories)
    print(f"\n[+] Ditemukan {len(categories)} kategori, {total_components} komponen total:\n")
    print(f"    {'No.':<5} {'Kategori':<25} {'Jumlah':<10} {'Komponen'}")
    print(f"    {'---':<5} {'---':<25} {'---':<10} {'---':<40}")
    for i, cat in enumerate(categories, 1):
        preview = ", ".join(cat["components"][:4])
        if len(cat["components"]) > 4:
            preview += ", ..."
        print(f"    {i:<5} {cat['category']:<25} {len(cat['components']):<10} {preview}")

    total_downloads = total_components * count_per_component
    print(f"\n    Total download maks: {total_components} x {count_per_component} = {total_downloads} file")
    print()

    # --- Konfirmasi ---
    if not auto_confirm:
        confirm = input("    Lanjutkan? (y/n): ").strip().lower()
        if confirm not in ("y", "ya", "yes"):
            print("\n[!] Dibatalkan oleh user.")
            return

    # --- Mulai proses ---
    start_time = time.time()
    all_summaries = []

    # Satu session untuk semua download (berbagi cookies)
    session = create_session()
    session.headers["Accept-Encoding"] = "gzip, deflate"
    human_delay(1.0, 2.0)

    try:
        for cat_idx, cat in enumerate(categories, 1):
            category = cat["category"]
            components = cat["components"]

            # Buat subfolder per kategori
            cat_folder = os.path.join(os.path.abspath(output_folder), category)
            if not os.path.exists(cat_folder):
                os.makedirs(cat_folder)

            cat_start = time.time()

            print(f"\n{'='*60}")
            print(f"  KATEGORI [{cat_idx}/{len(categories)}]: {category}")
            print(f"  Komponen: {len(components)} | Output: {cat_folder}")
            print(f"{'='*60}")

            for comp_idx, comp_name in enumerate(components, 1):
                print(f"\n  -- Komponen [{comp_idx}/{len(components)}]: {comp_name} --")

                summary = search_and_download(
                    session,
                    component_name=comp_name,
                    count=count_per_component,
                    download_folder=cat_folder,
                )
                summary["category"] = category
                all_summaries.append(summary)

                # Delay antar komponen
                if comp_idx < len(components):
                    human_delay(3.0, 6.0)

            cat_elapsed = time.time() - cat_start
            print(f"\n  [i] Kategori '{category}' selesai dalam {format_duration(cat_elapsed)}")

            # Delay antar kategori
            if cat_idx < len(categories):
                print(f"\n  [~] Jeda antar kategori...")
                human_delay(4.0, 8.0)

    except KeyboardInterrupt:
        print("\n\n[!] Dihentikan oleh user (Ctrl+C).")
    except Exception as e:
        print(f"\n[ERROR] Kesalahan fatal: {e}")

    # --- Laporan Akhir ---
    elapsed = time.time() - start_time

    print(f"\n{'#'*70}")
    print(f"  LAPORAN AKHIR")
    print(f"{'#'*70}")
    print(f"  Waktu total: {format_duration(elapsed)}\n")

    print(f"  {'Kategori':<22} {'Komponen':<16} {'Hasil':<14} {'Waktu':<10} {'Keterangan'}")
    print(f"  {'-'*22} {'-'*16} {'-'*14} {'-'*10} {'-'*20}")

    total_success = 0
    total_fail = 0
    total_skip = 0
    total_not_found = 0

    for s in all_summaries:
        cat_display = s.get("category", "")
        comp = s["component"]
        requested = s["requested"]
        elapsed_str = format_duration(s["elapsed"])

        if s["skipped_reason"]:
            hasil = f"0/{requested}"
            status = "[SKIP]"
            keterangan = s["skipped_reason"]
            total_skip += 1
            total_not_found += requested
        elif s["success"] == requested and s["fail"] == 0:
            hasil = f"{s['success']}/{requested}"
            status = "[OK]"
            keterangan = ""
            total_success += s["success"]
        elif s["fail"] > 0:
            hasil = f"{s['success']}/{requested}"
            status = "[PARTIAL]"
            keterangan = f"{s['fail']} gagal download"
            total_success += s["success"]
            total_fail += s["fail"]
            total_not_found += requested - s["success"] - s["fail"]
        else:
            # success < requested, fail == 0 -> hasil pencarian kurang
            hasil = f"{s['success']}/{requested}"
            status = "[PARTIAL]"
            keterangan = f"Hanya {s['success']} hasil ditemukan"
            total_success += s["success"]
            total_not_found += requested - s["success"]

        print(f"  {cat_display:<22} {comp:<16} {hasil:<14} {elapsed_str:<10} {status} {keterangan}")

    total_expected = len(all_summaries) * count_per_component

    print(f"\n  {'-'*70}")
    print(f"  Diminta     : {total_expected} file ({len(all_summaries)} komponen x {count_per_component})")
    print(f"  Berhasil    : {total_success}")
    print(f"  Gagal       : {total_fail}")
    print(f"  Tidak ada   : {total_not_found} (hasil pencarian kurang / komponen dilewati)")
    print(f"  Dilewati    : {total_skip} komponen")
    print(f"  Output      : {os.path.abspath(output_folder)}")
    print(f"{'#'*70}\n")


# ================================================================
# ENTRY POINT
# ================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Batch Datasheet Downloader (HTTP Mode)"
    )
    parser.add_argument("--count", type=int, help="Jumlah data per komponen")
    parser.add_argument("--yes", action="store_true", help="Lewati konfirmasi (y/n)")
    args = parser.parse_args()

    print()
    print("  +========================================+")
    print("  |   BATCH DATASHEET DOWNLOADER           |")
    print("  |   HTTP Mode (tanpa Playwright)         |")
    print("  |   Membaca komponen dari folder list/   |")
    print("  +========================================+")
    print()

    if args.count is not None:
        jumlah = args.count
    else:
        jumlah_input = input("  Jumlah data per komponen: ").strip()
        try:
            jumlah = int(jumlah_input)
        except ValueError:
            print("  [ERROR] Jumlah harus berupa angka.")
            sys.exit(1)

    if jumlah < 1:
        print("  [ERROR] Jumlah harus minimal 1.")
        sys.exit(1)

    batch_download(count_per_component=jumlah, auto_confirm=args.yes)
