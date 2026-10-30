"""
batch_download.py -- Manual Batch Datasheet Downloader (HTTP Mode)

Menerima input nama komponen secara manual dari user (tanpa membaca file list/).
Berjalan via HTTP (requests + BeautifulSoup) tanpa browser Playwright.
"""

import os
import sys
import time

from core.scraper import (
    format_duration,
    human_delay,
    create_session,
    search_component,
    download_single,
    sanitize_filename,
)


def manual_batch_download(components: list[str], count_per_component: int = 1, output_folder: str = "downloads"):
    """Download datasheet untuk daftar komponen hasil input manual user."""
    output_folder = os.path.abspath(output_folder)
    os.makedirs(output_folder, exist_ok=True)

    print(f"\n{'#'*60}")
    print(f"  MANUAL BATCH DATASHEET DOWNLOADER (HTTP Mode)")
    print(f"  Jumlah komponen     : {len(components)}")
    print(f"  Jumlah per komponen : {count_per_component}")
    print(f"  Folder output       : {output_folder}")
    print(f"{'#'*60}")

    start_time = time.time()
    all_summaries = []

    session = create_session()
    session.headers["Accept-Encoding"] = "gzip, deflate"
    human_delay(1.0, 2.0)

    try:
        for idx, comp_name in enumerate(components, 1):
            comp_start = time.time()
            print(f"\n[{idx}/{len(components)}] Memproses: {comp_name}")

            summary = {
                "component": comp_name,
                "requested": count_per_component,
                "success": 0,
                "fail": 0,
                "skipped_reason": None,
                "elapsed": 0.0,
            }

            human_delay(0.8, 1.8)
            results = search_component(session, comp_name, needed=count_per_component)

            if not results:
                print(f"    [!] Tidak ada hasil untuk '{comp_name}'. Dilewati.")
                summary["skipped_reason"] = "Tidak ada hasil pencarian"
                summary["elapsed"] = time.time() - comp_start
                all_summaries.append(summary)
                continue

            print(f"    [+] Ditemukan {len(results)} hasil, mulai unduh...")

            for i, res in enumerate(results, 1):
                filename = sanitize_filename(res["part_no"], res["manufacturer"])
                expected_file = os.path.join(output_folder, filename)

                if os.path.isfile(expected_file) and os.path.getsize(expected_file) > 1000:
                    print(f"    [SKIP] {res['part_no']} sudah ada ({os.path.getsize(expected_file)} bytes)")
                    summary["success"] += 1
                    continue

                ok = download_single(session, res, i, output_folder)
                if ok:
                    summary["success"] += 1
                else:
                    summary["fail"] += 1

                if i < len(results):
                    human_delay(1.5, 3.0)

            summary["elapsed"] = time.time() - comp_start
            all_summaries.append(summary)

            if idx < len(components):
                human_delay(2.5, 4.5)

    except KeyboardInterrupt:
        print("\n\n[!] Dihentikan oleh user (Ctrl+C).")
    except Exception as e:
        print(f"\n[ERROR] Terjadi kesalahan: {e}")

    # Laporan Akhir
    elapsed = time.time() - start_time
    print(f"\n{'#'*70}")
    print(f"  LAPORAN AKHIR")
    print(f"{'#'*70}")
    print(f"  Waktu total: {format_duration(elapsed)}\n")
    print(f"  {'Komponen':<20} {'Hasil':<14} {'Waktu':<10} {'Keterangan'}")
    print(f"  {'-'*20} {'-'*14} {'-'*10} {'-'*20}")

    total_success = 0
    total_fail = 0

    for s in all_summaries:
        comp = s["component"]
        requested = s["requested"]
        elapsed_str = format_duration(s["elapsed"])

        if s["skipped_reason"]:
            hasil = f"0/{requested}"
            status = "[SKIP]"
            ket = s["skipped_reason"]
        elif s["success"] == requested and s["fail"] == 0:
            hasil = f"{s['success']}/{requested}"
            status = "[OK]"
            ket = ""
            total_success += s["success"]
        else:
            hasil = f"{s['success']}/{requested}"
            status = "[PARTIAL]"
            ket = f"{s['fail']} gagal" if s['fail'] > 0 else f"Hanya {s['success']} ditemukan"
            total_success += s["success"]
            total_fail += s["fail"]

        print(f"  {comp:<20} {hasil:<14} {elapsed_str:<10} {status} {ket}")

    print(f"\n  Total berhasil: {total_success} | Total gagal: {total_fail}")
    print(f"  Folder output : {output_folder}\n")


if __name__ == "__main__":
    print()
    print("  +========================================+")
    print("  |   MANUAL BATCH DATASHEET DOWNLOADER    |")
    print("  |   HTTP Mode (tanpa browser Playwright) |")
    print("  +========================================+")
    print()

    # Input manual nama komponen dari user
    raw_input = input("  Masukkan nama komponen (pisahkan dengan koma jika > 1, misal: NE555, LM358): ").strip()
    if not raw_input:
        print("  [ERROR] Nama komponen tidak boleh kosong.")
        sys.exit(1)

    # Parsing komponen: pisahkan koma, strip whitespace, deduplikasi
    components = []
    seen = set()
    for item in raw_input.split(","):
        name = item.strip()
        if name and name.upper() not in seen:
            seen.add(name.upper())
            components.append(name)

    if not components:
        print("  [ERROR] Tidak ada nama komponen valid.")
        sys.exit(1)

    # Input jumlah data per komponen
    count_raw = input("  Jumlah data per komponen [default: 1]: ").strip()
    if not count_raw:
        count = 1
    else:
        try:
            count = int(count_raw)
            if count < 1:
                print("  [ERROR] Jumlah harus minimal 1.")
                sys.exit(1)
        except ValueError:
            print("  [ERROR] Jumlah harus berupa angka.")
            sys.exit(1)

    manual_batch_download(components, count_per_component=count)
