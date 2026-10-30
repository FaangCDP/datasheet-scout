# Project Checkpoint: Datasheet Downloader (`Learn_Py`)

Dokumen ini adalah checkpoint status proyek untuk melanjutkan pengembangan tanpa kehilangan konteks teknis atau mengulang analisis sebelumnya.

---

## 1. Tujuan dan Status Proyek Saat Ini
- **Tujuan Proyek:** Mengotomasi pencarian dan pengunduhan file datasheet komponen elektronik PDF dari situs `https://datasheet4u.com` secara massal (batch) berdasarkan daftar komponen per kategori pada file teks (`list/*.txt`).
- **Status Saat Ini:**
  - Varian HTTP (`batch_download_http.py` dan `download_datasheet_http.py`) telah diperbaiki dari bug kritis (path traversal, file korup HTML, missing Referer) dan telah dilengkapi fitur *skip existing* serta dukungan CLI `argparse`.
  - Telah tersedia 29 unit test mandiri pada `tests/test_batch_http.py` dengan status **100% PASS**.
  - Varian Playwright (`batch_download.py` dan `download_datasheet.py`) belum diselaraskan dengan patch tersebut.

---

## 2. Struktur Folder dan File Relevan
Lokasi root proyek: `/home/paang/Documents/Learn_Py`

```text
/home/paang/Documents/Learn_Py/
├── batch_download_http.py         # Skrip orkestrasi batch mode HTTP (SUDAH DIPATCH)
├── download_datasheet_http.py     # Modul download & scraping mode HTTP (SUDAH DIPATCH)
├── batch_download.py              # Skrip orkestrasi batch mode Playwright (BELUM DIPATCH)
├── download_datasheet.py          # Modul download mode Playwright (BELUM DIPATCH)
├── list/
│   └── Microcontroller.txt        # Daftar komponen kategori Microcontroller
├── downloads/                     # Folder output file PDF hasil unduhan
│   ├── Microcontroller/           # Contoh subfolder per kategori
│   └── *.pdf                      # File datasheet tersimpan
├── tests/
│   └── test_batch_http.py         # Unit test suite mandiri (29 test cases)
├── PANDUAN_INSPECT_HTTP.md        # Catatan hasil inspect DOM & network datasheet4u.com
├── PERUBAHAN.md                   # Catatan rencana evaluasi awal
├── requirements.txt           # File dependensi pip (requests, beautifulsoup4)
├── implementation.md          # Checkpoint ini
```
*Catatan:* Direktori `venv/` sudah dibuat ulang untuk lingkungan Linux aktif dengan `requests` dan `beautifulsoup4` terpasang.

---

## 3. Arsitektur dan Alur Kerja Program
Alur kerja pada varian HTTP (`batch_download_http.py`):
1. **Inisialisasi & Scan:** Fungsi `scan_list_folder()` memindai folder `list/` untuk membaca semua file `.txt`. Nama file menjadi nama kategori.
2. **Parsing List:** `read_component_file()` membaca tiap baris, membersihkan whitespace, mengabaikan komentar (`#`), serta menghapus duplikasi (case-insensitive).
3. **Session Tunggal:** `create_session()` membuat satu objek `requests.Session` yang mengunjungi homepage untuk mengumpulkan cookies awal.
4. **Pencarian Komponen:** `search_component()` melakukan `GET /share_search.php?sWord={komponen}` dan mem-parsing tabel HTML `table.search-results` untuk mengambil link detail (`a.line`).
5. **Cek Skip Existing:** Sebelum mengunduh, diperiksa apakah file `{safe_part}_{safe_mfr}_datasheet.pdf` sudah ada di folder tujuan dengan ukuran > 1000 bytes. Jika ya, download jaringan dilewati.
6. **Ekstraksi & Download PDF:**
   - Masuk ke halaman detail komponen (`/datasheets/...`).
   - Masuk ke halaman perantara unduh (`/download/...html`).
   - Mengambil URL PDF (`/pdf/...pdf`).
   - Request stream PDF dengan header `Referer` halaman download.
   - Validasi 4 byte pertama: harus diawali `b"%PDF-"`.
   - Streaming penyimpanan chunk ke disk (ukuran chunk 64 KB).
7. **Laporan Akhir:** Menampilkan tabel agregasi (berhasil, gagal, dilewati, waktu).

---

## 4. Keputusan Teknis yang Ditetapkan & Alasannya
1. **Prioritas Mode HTTP dibanding Playwright:**
   - *Alasan:* Mode HTTP jauh lebih ringan (tanpa beban rendering Chromium ~200MB RAM), lebih cepat, dan dapat berjalan di lingkungan headless Linux tanpa kebutuhan display server (X11/Wayland).
2. **Sanitasi `part_no` menggunakan Karakter Alfanumerik, Dash, dan Underscore:**
   - *Alasan:* Komponen elektronika sering memiliki notasi part seperti `LM358/NOPB` atau `PIC16F877A-I/P`. Karakter slash (`/`) menyebabkan OS menganggapnya sebagai subdirektori dan memicu `FileNotFoundError`.
3. **Validasi Magic Byte `b"%PDF-"` di Stream Awal:**
   - *Alasan:* Server proteksi seperti Cloudflare sering mengembalikan HTTP 200 OK berisi payload HTML (captcha/error). Jika langsung disimpan sebagai `.pdf`, file menjadi korup.
4. **Header `Referer` Wajib:**
   - *Alasan:* Mencegah potensi blokir hotlink / HTTP 403 Forbidden dari server CDN datasheet.
5. **CLI Argparse dengan Interaktif Fallback:**
   - *Alasan:* Memungkinkan skrip dijalankan otomatis lewat cronjob/skrip bash (`--count N --yes`) tanpa merusak alur input manual bagi pengguna terminal interaktif.

---

## 5. File yang Telah Diubah dan Ringkasannya

### A. `download_datasheet_http.py`
- Baris 243: Menambahkan header `Referer: download_url` pada pemanggilan `session.get(pdf_url, ...)`.
- Baris 248–252: Menambahkan sanitasi pada `part_no` (`safe_part`) selain `manufacturer` sebelum membentuk nama file.
- Baris 254–269: Membaca chunk pertama (`first_chunk`) dan memverifikasi `first_chunk.startswith(b"%PDF-")`. Jika bukan PDF, batalkan penulisan dan kembalikan `False`. Menuliskan `first_chunk` sebelum melanjutkan iterasi stream.

### B. `batch_download_http.py`
- Menambahkan import `argparse`.
- Baris 149–159: Menambahkan logika *skip existing* pada `search_and_download` sebelum memanggil `download_single`.
- Baris 178: Menambahkan parameter `auto_confirm: bool = False` pada fungsi `batch_download`.
- Baris 212–216: Melewati prompt konfirmasi jika `auto_confirm=True`.
- Baris 337–367: Mengganti blok `__main__` dengan `argparse` yang mengenali opsi `--count` dan `--yes`.

### C. `tests/test_batch_http.py` (Baru Ditambahkan)
- Berisi 29 unit test berbasis modul standar Python (`unittest`) yang memvalidasi fungsi sanitasi part_no, sanitasi manufacturer, parser file list, scan folder list, validasi magic byte PDF, dan logika skip existing file.

---

## 6. Fitur Selesai vs Belum Selesai

### Selesai:
- [x] Sanitasi nama file terhadap karakter ilegal (`/`, `\`, `:`, spasi).
- [x] Proteksi integritas PDF (tolak payload HTML Cloudflare/error 200 OK).
- [x] Header anti-hotlink (`Referer`).
- [x] Fitur resume / *skip existing file* (> 1000 bytes).
- [x] Dukungan CLI flag (`--count`, `--yes`).
- [x] Unit test suite mandiri (29 test lulus).

### Belum Selesai:
- [x] Pembuatan file `requirements.txt` standar di root proyek.
- [x] Virtual environment Linux (`venv/`) siap pakai dengan dependensi terpasang.
- [ ] Penyelarasan patch bug sanitasi dan magic byte ke versi Playwright (`download_datasheet.py` dan `batch_download.py`).
- [ ] Refactoring modul helper bersama (DRY: menghilangkan duplikasi fungsi `human_delay`, `format_duration`, `read_component_file` antar file).

---

## 7. Error / Masalah yang Belum Terselesaikan
1. **Versi Playwright Masih Rentan Bug:**
   - `download_datasheet.py` dan `batch_download.py` belum di-patch. Jika dijalankan di server tanpa layar atau mengunduh komponen bertanda slash (`/`), skrip Playwright masih akan mengalami crash.
2. **Ketergantungan Paket di Lingkungan Python:**
   - Paket `requests` dan `beautifulsoup4` sudah terpasang di environment aktif runtime, tetapi folder `venv/` lokal proyek adalah binary Windows yang usang dan belum dibuatkan virtual environment Linux yang bersih.

---

## 8. Perintah Menjalankan Program dan Pengujian

### A. Menjalankan Unit Test (Terverifikasi)
```bash
python3 -m unittest tests.test_batch_http -v
```
*Hasil:* `Ran 29 tests in 0.012s, OK` (Seluruh 29 test berhasil).

### B. Menjalankan Program Batch HTTP Secara Interaktif
```bash
python3 batch_download_http.py
```
*(Program akan meminta input jumlah data per komponen dan konfirmasi y/n)*.

### C. Menjalankan Program Batch HTTP Otomatis (Non-Interaktif)
```bash
python3 batch_download_http.py --count 1 --yes
```

### D. Verifikasi Bantuan Argumen CLI
```bash
python3 batch_download_http.py --help
```

---

## 9. Langkah Berikutnya yang Konkret
1. **Membuat `requirements.txt`:**
   Menulis file dependensi minimal (`requests>=2.28.0`, `beautifulsoup4>=4.11.0`, opsional: `playwright>=1.40.0`).
2. **Penyelarasan Varian Playwright (Bila Masih Ingin Digunakan):**
   Menerapkan patch sanitasi `part_no`, validasi `b"%PDF-"`, dan parameter `headless` dinamis pada `download_datasheet.py` & `batch_download.py`.
3. **Pembersihan Lingkungan Lokal:**
   Menghapus direktori `venv/` Windows yang usang dan menambahkan `.gitignore` untuk mengabaikan `downloads/`, `__pycache__/`, dan environment virtual.

---

## 10. Hal yang Tidak Boleh Diubah atau Diulang
- **Jangan Mengulang Analisis DOM Situs:** Struktur tag `datasheet4u.com` (`table.search-results`, `<a class="line">`, `span.mfr-name`, `a[href*='/download/']`, `<a href="/pdf/...">`) telah diverifikasi langsung via browser inspect live dan terbukti valid (lihat `PANDUAN_INSPECT_HTTP.md`).
- **Jangan Menghapus Header `Referer`:** Meskipun server saat ini terkadang mengizinkan direct request, ketiadaan Referer berisiko memicu HTTP 403 sewaktu-waktu.
- **Jangan Menghapus Sanitasi `part_no`:** Sanitasi ini wajib dipertahankan untuk menghindari crash sistem file pada penamaan komponen elektronik.
- **Jangan Mengubah Kode Tanpa Izin Eksplisit Pengguna:** Tetap ikuti preferensi pengguna: analisis dan rencanakan terlebih dahulu sebelum mengeksekusi modifikasi file.
