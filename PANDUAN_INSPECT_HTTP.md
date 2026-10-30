# Panduan Browser Inspect (DevTools) & Mitigasi Bug HTTP Scraping

Dokumen ini memuat panduan pemeriksaan browser inspect, **hasil verifikasi live DOM & network aktual dari `datasheet4u.com`**, serta titik kode spesifik yang harus diperbaiki pada `batch_download_http.py` (dan modul impor `download_datasheet_http.py`).

---

## 1. Hasil Live Inspect & Verifikasi Aktual dari Situs

Pemeriksaan live browser pada `datasheet4u.com` (diuji dengan komponen `NE555`) mengonfirmasi struktur berikut:

### A. Halaman Pencarian (`https://datasheet4u.com/share_search.php?sWord=...`)
- **Tabel Utama:** `table.search-results` (berhasil ditemukan).
- **Format Link Hasil:** Tag `<a class="line" href="/datasheets/{Brand}/{Part}/{ID}">`.
  - Contoh aktual: `<a class="line" href="/datasheets/STMicroelectronics/NE555/454332">NE555</a>`
- **Pabrikan:** `<span class="mfr-name">STMicroelectronics</span>`.
- **Kondisi Komponen Tidak Ditemukan:**
  - `table.search-results` tetap muncul di DOM (bukan hilang).
  - Tidak ada elemen `<a class="line">` (`count = 0`).
  - Teks di dalam tabel berbunyi: *"No data that matches perfectly! Reduce the number of words in the search term..."*.
  - *Catatan Kode:* Logika `if not links:` di `search_component` sudah tepat menangani kondisi ini.

### B. Halaman Detail Komponen (`/datasheets/{Brand}/{Part}/{ID}`)
- **Tautan ke Halaman Download:**
  - Selector: `a[href*='/download/']`
  - Contoh aktual: `<a href="/download/454332/NE555.html" target="_blank">`

### C. Halaman Download PDF (`/download/{ID}/{Part}.html`)
- **Tautan Berkas PDF:**
  - Tag teks unduh: `<a href="/pdf/454332/NE555.pdf">Download NE555 Datasheet PDF</a>`
  - Iframe pratinjau: `<iframe src="/pdf/454332/NE555.pdf">`
  - *Catatan Kode:* Selector `a` dengan filter teks `"Download"` dan `"Datasheet PDF"` terbukti valid di DOM asli.

### D. Hasil Uji Jaringan & Header Response (Network)
Pengujian HTTP GET langsung ke `https://datasheet4u.com/pdf/454332/NE555.pdf`:
- **HTTP Status:** `200 OK`
- **Content-Type:** `application/pdf`
- **Magic Bytes Header:** `b'%PDF-1.7\r\n%\xa1\xb3...'`
- **Perilaku Referer:** Saat ini server masih mengizinkan unduhan tanpa header `Referer`, namun penambahan `Referer: https://datasheet4u.com/download/...` sangat disarankan untuk proteksi anti-hotlink jangka panjang.

---

## 2. Bagian Kode yang Harus Diperbaiki (Daftar Baris Spesifik)

Perbaikan terfokus pada titik rawan berikut sebelum menjalankan batch:

### 1. Sanitasi `part_no` untuk Nama File
- **File & Baris:** `download_datasheet_http.py:249-251`
- **Masalah:** Karakter seperti `/` pada `part_no` (misal `LM358/NOPB`) akan memecah path direktori dan menyebabkan `FileNotFoundError`.
- **Perbaikan yang harus diterapkan:**
  ```python
  # Sanitasi part_no selain manufacturer
  safe_part = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in part_no).strip('_')
  safe_mfr = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in manufacturer).strip().replace(' ', '_')
  filename = f"{safe_part}_{safe_mfr}_datasheet.pdf"
  ```

### 2. Validasi Magic Byte PDF Sebelum Menyimpan
- **File & Baris:** `download_datasheet_http.py:256-261`
- **Masalah:** Jika respons berstatus 200 tetapi berupa HTML (Cloudflare challenge / captcha), script saat ini langsung menulisnya ke file `.pdf`.
- **Perbaikan yang harus diterapkan:**
  ```python
  # Ambil chunk pertama dan validasi magic bytes
  chunks = resp.iter_content(chunk_size=65536)
  first_chunk = next(chunks, b"")
  if not first_chunk.startswith(b"%PDF-"):
      print(f"      [ERROR] Respons bukan file PDF asli (terdeteksi HTML/error).")
      return False

  with open(file_path, "wb") as f:
      f.write(first_chunk)
      for chunk in chunks:
          if chunk:
              f.write(chunk)
  ```

### 3. Sertakan Header `Referer` pada Request PDF
- **File & Baris:** `download_datasheet_http.py:243`
- **Masalah:** Download PDF dipanggil tanpa context halaman perantara (`download_url`).
- **Perbaikan yang harus diterapkan:**
  ```python
  resp = session.get(pdf_url, headers={"Referer": download_url}, timeout=120, stream=True)
  ```

### 4. Fitur Skip Existing (Resume) pada Batch
- **File & Baris:** `batch_download_http.py:148-151` (di dalam `search_and_download`)
- **Masalah:** Komponen yang sudah selesai diunduh akan diunduh ulang jika batch di-restart.
- **Perbaikan yang harus diterapkan:**
  Sebelum memanggil `download_single()`, cek apakah file dengan awalan nama komponen sudah ada dan ukurannya > 1000 bytes di folder target.
