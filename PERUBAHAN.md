# Rencana Evaluasi & Perbaikan Khusus `batch_download_http.py`

Dokumen ini membedah arsitektur, struktur fungsi, temuan masalah, ketiadaan pengujian, serta usulan langkah perbaikan terarah khusus untuk **`batch_download_http.py`** tanpa menulis ulang seluruh proyek.

---

## 1. Struktur Kode & Penjelasan Fungsi

`batch_download_http.py` berfungsi sebagai *orchestrator* unduhan massal berbasis protokol HTTP murni (`requests` + `BeautifulSoup`).

### Diagram Alur Modul:
```text
batch_download_http.py
│
├── [Import Dependensi]
│   └── download_datasheet_http: BASE_URL, human_delay, format_duration,
│                                create_session, search_component, download_single
│
├── scan_list_folder(list_folder)
│   └── Memindai direktori list/ -> mengekstrak file *.txt sebagai kategori
│
├── read_component_file(file_path)
│   └── Membaca nama komponen dari file .txt, membersihkan spasi/komentar, deduplikasi
│
├── search_and_download(session, component_name, count, download_folder)
│   └── Mengatur pencarian & iterasi unduhan per komponen menggunakan session bersama
│
├── batch_download(count_per_component, list_folder, output_folder)
│   └── Loop kategori -> pembuatan subdirektori -> eksekusi unduh -> rekap & laporan
│
└── if __name__ == "__main__":
    └── Validasi input integer jumlah unduhan dari user
```

### Rincian Fungsi Internal:

1. **`scan_list_folder(list_folder: str) -> list[dict]`**
   - **Fungsi:** Membaca folder `list/` (default) dan mencari semua file berekstensi `.txt`.
   - **Output:** List dictionary: `[{"category": "Microcontroller", "file_path": "...", "components": [...]}, ...]`.
   - **Toleransi:** Mengabaikan file selain `.txt` dan file `.txt` yang kosong.

2. **`read_component_file(file_path: str) -> list[str]`**
   - **Fungsi:** Membaca nama komponen dari file `.txt` per baris.
   - **Fitur:** Mengabaikan baris kosong dan komentar (diawali `#`), deduplikasi dengan mempertahankan urutan (`seen.add(name_upper)`), serta menyediakan fallback pembacaan encoding `latin-1` jika UTF-8 gagal.

3. **`search_and_download(session, component_name: str, count: int, download_folder: str) -> dict`**
   - **Fungsi:** Mengambil daftar link dari `search_component()`, lalu menjalankan loop pemanggilan `download_single()`.
   - **Output:** Ringkasan statistik per komponen: `{"component", "requested", "success", "fail", "skipped_reason", "elapsed"}`.

4. **`batch_download(count_per_component: int, list_folder: str, output_folder: str)`**
   - **Fungsi:** Fungsi kendali utama batch. Menampilkan ringkasan daftar kategori, meminta konfirmasi `(y/n)`, membuka satu session HTTP bersama (`create_session`), membuat folder output tiap kategori, dan mencetak tabel laporan akhir.

---

## 2. Temuan Masalah & Keterbatasan pada `batch_download_http.py`

### A. Bug yang Berdampak Langsung
1. **Kegagalan Unduh pada Komponen Berkarakter Khusus (`part_no`):**
   - `batch_download_http.py` mengandalkan fungsi `download_single` dari `download_datasheet_http.py:249-253`.
   - Fungsi tersebut belum men-sanitasi `part_no`. Jika file list memiliki komponen dengan simbol seperti `/` (misal: `LM358/NOPB`, `PIC16F877A-I/P`), skrip crash dengan `FileNotFoundError` saat mencoba menyimpan file.
2. **Ketiadaan Validasi Integritas File PDF:**
   - Stream unduhan langsung ditulis ke file `.pdf`. Jika server membatasi koneksi atau menyajikan halaman verifikasi HTML berstatus 200 OK, batch tetap menyimpannya sebagai file `.pdf` korup.

### B. Bagian Belum Selesai (Incomplete)
1. **Fitur Resume / *Skip Existing* Belum Tersedia:**
   - Jika proses batch terputus di tengah jalan, eksekusi ulang akan mendownload kembali file yang sudah pernah diunduh, membuang kuota dan waktu.
2. **Ketergantungan Interaktif pada `input()`:**
   - Membutuhkan prompt konfirmasi `(y/n)` dan `input()` jumlah data di `__main__`, menyulitkan otomatisasi headless/cronjob.

### C. Pengujian yang Belum Tersedia
- Belum ada unit test otomatis untuk:
  - `read_component_file`: Menguji parsing file teks dengan komentar `#`, spasi ganda, case mismatch, dan deduplikasi.
  - `scan_list_folder`: Memastikan file non-`.txt` di folder `list/` dilewati dengan benar.
  - Penanganan komponen dengan karakter slash (`/`) agar tidak memecah direktori.

---

## 3. Usulan Langkah Perubahan Terarah (Tanpa Menulis Ulang)

### Langkah 1: Isolasi Sanitasi Nama & Validasi PDF
- Pastikan penyimpanan file di `download_single` (atau dibungkus langsung di dalam `batch_download_http.py`) membersihkan karakter ilegal pada `part_no`:
  ```python
  safe_part = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in part_no).strip('_')
  ```
- Periksa 4 byte pertama file hasil stream: jika tidak diawali `b"%PDF-"`, batalkan penulisan dan kembalikan status gagal.

### Langkah 2: Tambahkan Cek Keberadaan File (*Skip Existing*)
- Di dalam `search_and_download`, tambahkan pengecekan sebelum `download_single`:
  - Jika file PDF komponen terkait sudah ada di folder tujuan dan ukurannya > 1 KB, catat sebagai sukses (*cached*) dan lewati download jaringan.

### Langkah 3: Dukungan Flag CLI Opsional
- Modifikasi blok `__main__` agar dapat menerima argumen terminal:
  ```bash
  python batch_download_http.py --count 2 --yes
  ```
  Jika argumen tidak diberikan, tetap gunakan prompt interaktif `input()` default.

### Langkah 4: Tambahkan File Pengujian Mandiri (`tests/test_batch_http.py`)
- Buat test berbasis `unittest` (stdlib) untuk menguji parsing list komponen dan sanitasi nama file tanpa memerlukan koneksi internet.
