# Checkpoint Proyek: Datasheet Downloader (`Learn_Py`)

Dokumen ini mencatat ringkasan status proyek, akar masalah bug pencarian yang baru saja diselesaikan, seluruh perubahan yang telah diterapkan, serta hasil verifikasi riil agar model AI berikutnya dapat langsung memahami dan melanjutkan proyek.

---

## 1. Ringkasan Akar Masalah Bug "Pencarian Cepat / 0 Hasil"

### Gejala:
Proses batch berjalan terlalu cepat (0–1 detik per komponen) dan seluruh komponen dilaporkan `[SKIP] Tidak ada hasil pencarian` padahal komponen tersebut sangat populer (misal: `ATmega328P`, `ESP32`).

### Akar Masalah Teknis (Root Cause):
1. Modul `download_datasheet_http.py` mendefinisikan header:
   `"Accept-Encoding": "gzip, deflate, br"`
2. Karena header tersebut secara eksplisit menyatakan dukungan `br` (Brotli), server Cloudflare mengembalikan respons terkompresi Brotli (`Content-Encoding: br`).
3. Modul Python `requests` bawaan **tidak mendukung dekompresi Brotli** jika paket C `brotli` / `brotlicffi` tidak terpasang.
4. `requests` gagal mendekompresi payload secara otomatis, sehingga atribut `resp.text` berisi data biner mentah (*corrupted binary string*).
5. Parser `BeautifulSoup(resp.text, "html.parser")` tidak dapat menemukan elemen DOM `table.search-results`.
6. Fungsi `search_component()` selalu mengembalikan `[]` secara instan, memicu status `[SKIP]` tanpa pernah melakukan pencarian nyata.

---

## 2. Perubahan yang Telah Diterapkan

### A. Perbaikan pada `batch_download_http.py` (Khusus Tugas Terakhir)
- **Override Header Kompresi:**
  Menimpa konfigurasi header impor agar hanya menerima encoding standar yang didukung native oleh `requests`:
  ```python
  import download_datasheet_http
  download_datasheet_http.HEADERS["Accept-Encoding"] = "gzip, deflate"
  ```
- **Penegakan Header Sesi:**
  Memastikan session pada `batch_download()` dan `search_and_download()` menggunakan `session.headers["Accept-Encoding"] = "gzip, deflate"`.
- **Dukungan CLI Argparse:**
  Menerima opsi `--count N` dan `--yes` (non-interaktif untuk otomasi), dengan fallback otomatis ke input manual jika flag tidak diberikan.
- **Fitur Skip Existing File:**
  Mengecek file `{safe_part}_{safe_mfr}_datasheet.pdf` di folder tujuan. Jika file sudah ada dan ukurannya > 1000 bytes, download dilewati untuk menghemat kuota jaringan.

### B. Perubahan pada `batch_download.py` (Mode Manual HTTP)
- **Konversi ke HTTP Murni (Tanpa Playwright):** Menghapus dependensi `playwright` dan browser automation, menggantikannya dengan modul HTTP (`requests` + `BeautifulSoup`).
- **Input Manual (Tanpa Pembacaan File):** Tidak lagi membaca folder `list/`. User memasukkan nama komponen secara manual via prompt terminal (mendukung satu atau banyak komponen sekaligus dipisahkan dengan koma, misal: `NE555, LM358`).
- **Mitigasi Kompresi Brotli:** Menegakkan `download_datasheet_http.HEADERS["Accept-Encoding"] = "gzip, deflate"`.
- **Fitur Skip Existing File:** Otomatis memeriksa file yang sudah ada di folder `downloads/` (> 1000 bytes) agar tidak mengunduh ulang.
- **Hasil Uji Riil:** Diuji dengan input `NE555, LM358` (count=1). Run pertama: berhasil mengunduh 2 file PDF valid. Run kedua: kedua file dilewati secara otomatis (`[SKIP] sudah ada`).

### C. Perubahan Kumulatif Sebelumnya pada Proyek
1. **`download_datasheet_http.py`:**
   - Menambahkan header `Referer: download_url` pada request PDF untuk mencegah proteksi anti-hotlink (HTTP 403).
   - Sanitasi nama part (`safe_part`) selain `manufacturer` untuk mencegah crash `FileNotFoundError` akibat karakter slash (`/`) pada part number elektronika (contoh: `LM358/NOPB`).
   - Validasi magic byte `b"%PDF-"` pada chunk awal respons sebelum menyimpan ke file `.pdf` untuk mencegah tersimpannya payload HTML Cloudflare sebagai file rusak.
2. **Lingkungan & Dependensi:**
   - Dibuat ulang virtual environment Linux di `/home/paang/Documents/Learn_Py/venv`.
   - Terpasang dependensi resmi: `requests>=2.34.0` dan `beautifulsoup4>=4.15.0`.
   - Dibuat file spesifikasi `requirements.txt`.
3. **Pengujian (`tests/test_batch_http.py`):**
   - 29 unit test mandiri menggunakan pustaka standar `unittest` mencakup sanitasi nama file, parsing file teks komponen, penanganan error, validasi magic byte PDF, dan logika skip existing file.

---

## 3. Hasil Pengujian Riil (Verified Execution)

Perintah yang dijalankan:
```bash
cd /home/paang/Documents/Learn_Py && venv/bin/python batch_download_http.py --count 1 --yes
```

### Hasil Laporan Akhir:
```text
######################################################################
  LAPORAN AKHIR
######################################################################
  Waktu total: 1m 58s

  Kategori               Komponen         Hasil          Waktu      Keterangan
  ---------------------- ---------------- -------------- ---------- --------------------
  Microcontroller        ATmega328P       1/1            23s        [OK] 
  Microcontroller        ATmega2560       1/1            13s        [OK] 
  Microcontroller        ATmega32         1/1            10s        [OK] 
  Microcontroller        ATtiny85         1/1            1s         [OK] 
  Microcontroller        PIC16F877A       1/1            1s         [OK] 
  Microcontroller        PIC18F4550       1/1            9s         [OK] 
  Microcontroller        STM32F103C8      1/1            1s         [OK] 
  Microcontroller        ESP8266          1/1            1s         [OK] 
  Microcontroller        ESP32            1/1            9s         [OK] 
  Microcontroller        Arduino Nano     0/1            1s         [SKIP] Tidak ada hasil pencarian

  ----------------------------------------------------------------------
  Diminta     : 10 file (10 komponen x 1)
  Berhasil    : 9
  Gagal       : 0
  Tidak ada   : 1 (hasil pencarian kurang / komponen dilewati)
  Dilewati    : 1 komponen
  Output      : /home/paang/Documents/Learn_Py/downloads
######################################################################
```

*Catatan Verifikasi:*
- 9 dari 10 komponen berhasil diunduh dan tersimpan di `/home/paang/Documents/Learn_Py/downloads/Microcontroller/`.
- `Arduino Nano` dilewati karena merupakan board modul/development kit, bukan nomor IC komponen mandiri di database `datasheet4u.com`.

### D. Arsitektur Modular & Integrasi Bot Discord
- **Pembersihan File Lama:** `download_datasheet.py` dan `download_datasheet_http.py` telah dihapus.
- **Modul Inti `core/scraper.py`:** Logika scraper (pencarian, unduh PDF, sanitasi filename, bypass Cloudflare Brotli) dipindahkan ke `core/scraper.py` agar dapat digunakan bersama oleh skrip CLI dan Bot.
- **Bot Discord (`bots/discord/`):**
  - Menggunakan slash commands native murni tanpa prefix:
    - `/datasheet <komponen>`: Mencari komponen dan mengunggah PDF datasheet ke chat (jika <= 25 MB).
    - `/ping`: Menampilkan latensi bot (ms).
    - `/purge <jumlah>`: Menghapus sejumlah pesan di channel (maks 100 pesan, verifikasi izin `Manage Messages`).
  - Konvensi Modularitas (1 File = 1 Command):
    - `cogs/datasheet_cog.py`: Khusus command `/datasheet` (menerima input teks opsional `komponen` ATAU lampiran opsional `file` .txt; mengemas batch ke arsip .ZIP).
    - `cogs/ping_cog.py`: Khusus command `/ping` (cek latensi gateway Discord).
    - `cogs/purge_cog.py`: Khusus command `/purge` (hapus 1-100 pesan, verifikasi izin Manage Messages).
    - `cogs/help_cog.py`: Khusus command `/help` (panduan interaktif seluruh slash command dan multi-database).
    - `cogs/info_cog.py`: Khusus command `/info` (statistik sistem, runtime, ringkasan cache PDF, dan daftar database sumber aktif: `datasheet4u.com` & `alldatasheet.com`).
    - `bot.py` menggunakan auto-discovery (`glob("*_cog.py")`), sehingga penambahan command baru cukup dengan membuat file `<nama>_cog.py` di folder `cogs/` tanpa perlu mengedit `bot.py`.
  - Berjalan non-blocking menggunakan `asyncio.to_thread` agar gateway Discord tidak terputus saat request jaringan.
### E. Pembentukan Folder Database Sumber (`sources/`)
- **Tujuan:** Memisahkan konfigurasi URL, header HTTP, cookies, dan logika scraping spesifik per website agar arsitektur modular dan siap ditambah website sumber baru kapan saja.
- **Modul Sumber 1 (`sources/datasheet4u.py`):**
  - `BASE_URL = "https://datasheet4u.com"`
  - `HEADERS` dengan `Accept-Encoding: gzip, deflate` (tanpa Brotli)
  - Parsing tabel DOM `table.search-results a.line`
  - Download PDF via `/download/{id}/{part}.html` -> `/pdf/{id}/{part}.pdf`

- **Modul Sumber 2 (`sources/alldatasheet.py`) [BARU]:**
  - `BASE_URL = "https://www.alldatasheet.com"`
  - **Tantangan & Mitigasi Cloudflare WAF:**
    - Standard `requests` terblokir HTTP 403 akibat TLS fingerprinting Cloudflare.
    - Menggunakan `curl_cffi` dengan `impersonate="chrome124"` dan inisialisasi session homepage untuk memperoleh cookie `__cf_bm`.
  - **Alur Scraping & Resolusi PDF:**
    - Pencarian: `/view.jsp?Searchword={komponen}` -> parse link `/datasheet-pdf/pdf/...`
    - Resolusi Viewer: Ubah URL detail menjadi viewer pada host yang sama (`/datasheet-pdf/view/...`). Kunjungi detail page terlebih dahulu untuk men-generate tracking cookies (`chk`, `JSESSIONID`), lalu buka viewer page.
    - Ekstraksi PDF: Membaca parameter `file=` pada iframe `viewer.html?file=...` untuk memperoleh tautan langsung PDF.
    - Unduh: GET stream dengan header `Referer` viewer page, verifikasi magic byte `b"%PDF-"`.
  - **Pengujian Riil:** Diuji langsung pada `NE555`, `LM358`, dan `BC547`, seluruhnya menghasilkan file PDF valid 100%.

- **Struktur File Saat Ini:**
  ```text
  Learn_Py/
  ├── sources/
  │   ├── __init__.py
  │   ├── datasheet4u.py
  │   └── alldatasheet.py
  ├── core/
  │   ├── __init__.py
  │   ├── scraper.py
  │   ├── preview_extractor.py
  │   ├── specs_extractor.py
  │   ├── pinout_extractor.py
  │   └── package_classifier.py
  ├── bots/
  │   └── discord/
  │       ├── __init__.py
  │       ├── config.py
  │       ├── bot.py
  │       ├── .env.example
  │       └── cogs/
  │           ├── __init__.py
  │           ├── datasheet_cog.py
  │           ├── pinout_cog.py
  │           ├── panel_cog.py
  │           ├── myid_cog.py
  │           ├── help_cog.py
  │           ├── info_cog.py
  │           ├── ping_cog.py
  │           └── purge_cog.py
  ├── batch_download.py
  ├── batch_download_http.py
  ├── list/
  ├── downloads/
  ├── tests/
  ├── requirements.txt
  └── checkpoint.md
  ```

### F. Perbaikan Fallback & Penamaan Cache Multi-Source pada Bot Discord
- **Masalah:** Bot Discord tidak menemukan file cache atau gagal mendownload saat beralih ke `alldatasheet.com` karena nama file cache yang dicari (`_datasheet.pdf`) tidak sesuai dengan nama file keluaran `alldatasheet` (`_alldatasheet.pdf`).
- **Perbaikan:** `bots/discord/cogs/datasheet_cog.py` diperbarui agar menyertakan parameter `source = res.get("source", "datasheet4u")` saat memanggil `sanitize_filename(part_no, mfr, source=source)`.
- **Hasil:** Kompatibilitas nama cache dan download PDF untuk kedua sumber (`datasheet4u` & `alldatasheet`) kini sepenuhnya sinkron.

### G. Perbaikan PDF Dummy Error pada AllDatasheet (`sources/alldatasheet.py`)
- **Akar Masalah:**
  1. `urllib.parse.parse_qs` men-decode token URL terenkripsi (`%2B` berubah menjadi `+`), sehingga token otorisasi PDF ditolak server AllDatasheet.
  2. Header `Referer` pada request PDF sebelumnya mengarah ke halaman HTML biasa, bukan ke URL internal iframe `pdfjsview/web/viewer.html`.
  3. Server AllDatasheet membalas dengan PDF dummy berukuran tepat 25.307 bytes yang berisi gambar teks *"The AllDatasheet.com website is temporarily unavailable. please try back later. We apologize for any inconvenience"*.
- **Perbaikan yang Diterapkan:**
  1. URL PDF diekstrak langsung dari atribut `src` iframe tanpa decode agar karakter `%2B` tetap utuh.
  2. Request download PDF dikirim dengan header `Referer` merujuk ke URL viewer iframe yang bersangkutan.
  3. Ditambahkan validasi pencegahan: file dengan ukuran persis 25.307 bytes otomatis ditolak sebagai PDF dummy error.
- **Hasil Pengujian Riil:**
  - `Arduino Nano`: Berhasil mengunduh PDF manual asli berukuran 175.984 bytes (bukan lagi dummy 25 KB).
  - `NE555`: Berhasil mengunduh PDF datasheet Philips berukuran 132.353 bytes.

### H. Relevance Ranking & Ekstraksi Gambar Preview Cover PDF
- **Relevance Ranking (`core/scraper.py`):**
  - Ditambahkan fungsi pembobotan kecocokan nama part (`compute_relevance(item, query)`).
  - Kasus seperti `"Arduino Uno"` kini diprioritaskan mencocokkan `ARDUINO-UNO` (skor 100), bukan lagi mengambil urutan pertama yang tidak relevan (`ARDUINO-NANO`, skor 30).
  - Jika pencarian di `datasheet4u` hanya menghasilkan skor rendah (< 50, misal hanya cocok substring nama pabrikan seperti SUNON pada query `Uno`), sistem secara otomatis mengalihkan (*auto-fallback*) ke `alldatasheet.com`.
- **Modul Ekstraksi Preview Terpisah (`core/preview_extractor.py`):**
  - Menggunakan binary native `pdftoppm` untuk merender halaman pertama (cover/pinout) PDF menjadi gambar thumbnail PNG (skala lebar 300px).
  - Terisolasi penuh: jika `pdftoppm` gagal atau file PDF rusak, fungsi mengembalikan `None` dan bot tetap mengirimkan berkas PDF tanpa gangguan/crash.
- **Pembaruan Parameter Command `/datasheet` (`cogs/datasheet_cog.py` & `cogs/help_cog.py`):**
  - `komponen: str` (*Wajib*): Nama komponen yang dicari.
  - `kemasan: str = None` (*Opsional*): Bentuk fisik/package komponen (`DIP`, `SOIC`, `TO-92`, `TO-220`, dll.) dengan autocomplete instan.
  - `jumlah: int = 1` (*Opsional*, default = 1): Jumlah varian datasheet yang ingin diunduh. Jika meminta lebih dari 1 file, bot otomatis mengemas seluruh varian ke dalam file `.zip`.
  - `file: discord.Attachment = None` (*Opsional*): Lampiran file `.txt` berisi daftar komponen tambahan untuk unduhan batch otomatis.
  - Thumbnail halaman pertama PDF otomatis disematkan di pojok kanan atas embed (`embed.set_thumbnail(url="attachment://thumb_preview.png")`).
  - Cache filter diperketat agar file dummy berukuran 25.307 bytes tidak pernah disajikan dari cache.

### I. Autocomplete Real-Time & Ekstraksi Spesifikasi Kunci (Tahap 1 & 2)
- **Tahap 1: Autocomplete Cepat (`@datasheet.autocomplete('komponen')`):**
  - Menggabungkan katalog komponen praktikum umum (mikrokontroler, op-amp, timer, transistor, IC logika) dengan nama part di `list/*.txt` dan file PDF di `downloads/`.
  - Beroperasi secara in-memory (< 1ms), memastikan tidak terkena batas waktu timeout interaksi Discord (3 detik).
  - Mengembalikan maksimal 25 saran relevan dengan prioritas *prefix match* diikuti *contains match*.
- **Tahap 2: Ekstraksi Spesifikasi Kunci (`core/specs_extractor.py`):**
  - Modul mandiri terpisah yang memindai teks 3 halaman awal PDF menggunakan `pdftotext`.
  - Mengekstrak parameter kunci:
    - **Tegangan Kerja:** Rentang supply voltage (misal `3V to 36V`, `2.0V-5.5V`).
    - **Frekuensi/Clock:** Frekuensi osilator/CPU (misal `16 MHz`, `20 MHz`, `2.4 GHz`).
    - **Kemasan/Package:** Tipe kemasan (misal `SOIC, TSSOP, SOT-23`, `DIP-8`).
    - **Suhu Operasi:** Rentang temperatur kerja (misal `-40°C to +85°C`).
  - Nilai yang ditemukan otomatis disematkan sebagai field pada Embed Discord. Jika tidak ditemukan, embed tetap tampil bersih tanpa error.

### J. Command `/pinout` & Ekstraksi Diagram Kaki Komponen (Tahap 3)
- **Modul Deteksi Pinout (`core/pinout_extractor.py`):**
  - Memindai dokumen PDF untuk mendeteksi halaman yang memuat pola terminologi susunan kaki IC/komponen:
    - `pin configurations`, `pin layouts`, `pin assignments`, `pin descriptions`, `connection diagrams`, `pinout`, `terminal functions`.
  - Merender halaman yang terdeteksi menjadi file gambar PNG resolusi tinggi (150 DPI) di direktori `downloads/.pinouts/`.
  - Terisolasi penuh: jika dokumen tidak memuat diagram atau binary tidak tersedia, fungsi mengembalikan `(None, None)` tanpa membuat program error.
- **Slash Command Modular (`bots/discord/cogs/pinout_cog.py`):**
  - Menerapkan konvensi 1 file = 1 command (`/pinout <komponen>`).
  - Dilengkapi autocomplete real-time `@pinout.autocomplete('komponen')`.
  - Menampilkan gambar diagram kaki beresolusi tajam langsung di chat Discord via embed (`embed.set_image(url="attachment://pinout.png")`) beserta informasi halaman asal diagram.
- **Hasil Pengujian Riil:**
  - `LM358AP`: Berhasil menemukan dan merender diagram pinout pada Halaman 2 (226 KB PNG).
  - `ARDUINO-UNO`: Berhasil menemukan dan merender diagram connector pinout pada Halaman 9 (185 KB PNG).
  - `NE555`: Berhasil menemukan diagram pinout pada Halaman 1 (256 KB PNG).
  - Total 6 slash commands bot Discord (`datasheet`, `help`, `info`, `ping`, `pinout`, `purge`) berhasil di-load dan diverifikasi 100%.

### K. Fitur Pilihan Kemasan Interaktif via Tombol Discord (`pilihan_kemasan`)
- **Modul Pemilah Kemasan (`core/package_classifier.py`):**
  - Membersihkan suffix kemasan dari input (`clean_base_component`), contoh: `LM358D` / `LM358N` $\rightarrow$ `LM358`.
  - Mengelompokkan hasil pencarian ke dalam kemasan fisik unik (`select_distinct_packages`): `DIP`, `SOIC`, `TSSOP`, `MSOP`, `QFN`, `TO-92`, `TO-220`, dll.
- **Tampilan Interaktif UI Discord (`PackageSelectionView` di `cogs/datasheet_cog.py`):**
  - Parameter baru: `pilihan_kemasan: bool = False` pada slash command `/datasheet`.
  - **Hemat Ruang Disk & Kuota:** Bot tidak langsung mengunduh file, melainkan hanya menampilkan kartu embed berisi daftar kemasan yang tersedia beserta tombol Discord (`discord.ui.Button`):
    - Contoh: `[📦 DIP (LM358AP)]`, `[📦 SOIC (LM358DT)]`, `[📦 QFN (LM358QT)]`, dan tombol `[📦 Unduh Semua (ZIP)]`.
  - File PDF baru diunduh saat user mengklik salah satu tombol kemasan yang diinginkan.
- **Hasil Pengujian Riil:**
  - `clean_base_component("LM358D")` menghasilkan basis bersih `LM358`.
  - Pilihan 5 kemasan unik (`DIP`, `SOIC`, `QFN`, `TSSOP`, `MSOP`) berhasil dideteksi dari database dan tombol interaktif ter-generate 100% OK.
  - Seluruh 29 unit test tetap berstatus **100% PASS**.

### L. Command Panel Kontrol Server & Manajemen Disk Khusus Owner (`/panel`)
- **Keamanan & Otorisasi (`bots/discord/cogs/panel_cog.py`):**
  - Menggunakan variabel lingkungan `OWNER_ID` di `.env` (fallback otomatis ke owner aplikasi Discord via API).
  - Akses non-owner langsung ditolak secara aman dengan pesan *ephemeral*.
- **Dashboard Tombol Interaktif (`OwnerPanelView`):**
  - **Auto-Refresh Realtime:** Panel otomatis memperbarui embed status setiap 1 menit (60 detik) untuk mencegah blokir 403 Cloudflare, dengan sesi aktif selama 15 menit (`timeout = 900.0`).
  - **Latensi & Health Check Jaringan:**
    - Latensi Gateway Discord (`ms`).
    - Status ping/konektivitas ke `datasheet4u.com` (status HTTP & latensi ms).
    - Status ping/konektivitas ke `alldatasheet.com` (status HTTP & latensi ms).
  - **Monitoring VPS:** Menampilkan status pemakaian Disk (`GB` dan persentase), RAM (`GB`), dan load average CPU secara *real-time*.
  - **Tombol `[📜 Lihat Isi Disk]`:** Menampilkan daftar file PDF tersimpan di folder `downloads/` dan menyediakan menu dropdown (`discord.ui.Select`) untuk memilih serta menghapus file PDF tertentu secara selektif.
  - **Tombol `[🧹 Hapus Thumbnail & Pinout]`:** Menghapus seluruh file gambar cache sementara (`.thumbnails/` dan `.pinouts/`) untuk menghemat kapasitas disk.
  - **Tombol `[⚡ Sync Command Tree]`:** Menjalankan sinkronisasi slash command (`tree.sync()`) langsung dari antarmuka Discord.
- **Hasil Pengujian Riil:**
  - Auto-discovery memuat 8 slash commands (`datasheet`, `help`, `info`, `myid`, `panel`, `ping`, `pinout`, `purge`).
  - Pemantauan VPS dan penghitungan ukuran disk berjalan 100% akurat.
  - Seluruh 29 unit test tetap berstatus **100% PASS**.

### M. Pembaruan Command `/purge` (Otomatis & Auto-Delete 5 Detik)
- Parameter `jumlah: int = 10` dibuat opsional (default menghapus 10 pesan terakhir di channel).
- Bot menghitung dan menghapus pesan di detik tersebut, lalu mengirimkan pesan konfirmasi publik.
- Pesan konfirmasi otomatis dihapus setelah 5 detik (`await asyncio.sleep(5) -> delete()`) agar channel chat tetap bersih.

### N. Slash Command Sederhana `/myid` (`bots/discord/cogs/myid_cog.py`)
- Membaca ID akun Discord user yang menjalankan perintah (`interaction.user.id`).
- Format respon singkat dan bersih: `DiscordID: <user_id>` (pesan privat *ephemeral*).

### O. Inisialisasi Git & Perlindungan Secret (.gitignore)
- File `.gitignore` dibuat untuk menyaring `.env`, `venv/`, `downloads/`, cache gambar, dan bytecode `__pycache__`.
- Repository Git lokal telah diinisialisasi pada branch `main` dengan commit awal.
- GitHub CLI (`gh`) versi 2.103.3 telah dipasang di `~/.local/bin/gh`.

---

## 4. Panduan Eksekusi untuk Pengembang Berikutnya

### Mengaktifkan Environment
```bash
cd /home/paang/Documents/Learn_Py
source venv/bin/activate
```

### Menjalankan Unit Test
```bash
python -m unittest tests.test_batch_http -v
```

### Menjalankan Batch Downloader HTTP
```bash
# Mode pembacaan file daftar list/ otomatis:
python batch_download_http.py --count 1 --yes

# Mode input manual user (tanpa file):
python batch_download.py
```

### Menjalankan Bot Discord
```bash
# 1. Salin file environment dan isi token:
cp bots/discord/.env.example .env
# Edit .env dan masukkan DISCORD_TOKEN=...

# 2. Jalankan bot:
python -m bots.discord.bot
```

---

## 5. Pekerjaan Lanjutan yang Tersisa
1. **Integrasi Bot WhatsApp:**
   Menunggu referensi dari user untuk membuat `bots/whatsapp/` menggunakan modul `core.scraper` yang sama.
2. **Penyediaan Token Discord:**
   Mengisi `DISCORD_TOKEN` pada file `.env` untuk menjalankan bot secara live di server Discord.
