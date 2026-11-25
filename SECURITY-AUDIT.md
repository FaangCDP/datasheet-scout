# Security Audit — Learn_Py (Datasheet Scout)

Tanggal: 2026-11-24
Scope: seluruh code base `/home/paang/Documents/Learn_Py` (kecuali `venv/`, `__pycache__/`)
Metode: static review (baca source) + grep pola secret/URL/cleanup + cek permission file & git history
Status: **LAPORAN SAJA — belum ada satu baris code yang diubah.**

Ringkasan: **2 temuan TINGGI**, **3 temuan SEDANG**, **6 temuan RENDAH**. Tidak ditemukan token/secret hardcoded dan `.env` tidak pernah masuk git. Risiko terbesar bukan pencurian data, tapi **service tak bisa dipakai (DoS)**: siapa pun yang bisa memakai slash command bisa menghabiskan disk VPS 5 GB dan mematikan bot, karena tidak ada rate limit, tidak ada batas ukuran unduhan, dan cache tidak pernah dibersihkan otomatis.

---

## A. TINGGI — fatal kalau tidak ditambal

### H-01. Command publik tanpa rate limit + cache tak pernah di-prune → disk VPS penuh, bot mati

| Item | Detail |
|---|---|
| Lokasi | `bots/discord/cogs/datasheet_cog.py:382`, `:457`, `bots/discord/cogs/pinout_cog.py`, `core/scraper.py` |
| Bukti | `target_count = max(5, min(jumlah, 50))` — satu perintah bisa unduh sampai 50 PDF. `MAX_BATCH = 10` → 10 komponen × 50 = 500 PDF dalam satu kali `/datasheet file:`. Tidak ada `@app_commands.checks.cooldown` di **seluruh** cog (grep: nol hasil). Cache hanya dibersihkan manual lewat tombol owner (`panel_cog.py:347`). |
| Dampak | Semua member di semua guild tempat bot diundang bisa mengulang perintah tanpa jeda. Setiap request menulis PDF permanen ke `downloads/`. Disk 5 GB habis → bot crash, SQLite/cache korup, dan kalau bot di-hosting (Pterodactyl) proses mati total. Bonus: kuota proxy residensial terbakar. |
| Fix minimum | 1) `@app_commands.checks.cooldown(2, 60, key=app_commands.BucketType.user)` di `/datasheet`, `/pinout`, `/random`. 2) Prune otomatis: hapus cache lebih tua dari 24 jam / total folder > N MB saat startup + tiap request. 3) Quota harian per user. |

### H-02. Unduhan tanpa batas ukuran — `MAX_FILE_SIZE_MB` tidak membatasi download

| Item | Detail |
|---|---|
| Lokasi | `sources/alldatasheet.py:257`, `:282`; `sources/datasheet4u.py:189`; `bots/discord/cogs/datasheet_cog.py:96` |
| Bukti | `config.MAX_FILE_SIZE_MB` **hanya** dipakai untuk memutuskan apakah file di-attach ke Discord (`datasheet_cog.py:96`), bukan untuk membatasi unduhan. `alldatasheet.py:257` mengambil `r_pdf.content` utuh ke RAM tanpa cek `Content-Length` → satu respons besar = `MemoryError` (bot OOM). `datasheet4u.py:189` pakai `stream=True` + `iter_content` **tanpa cap byte** → tulis ke disk sampai habis. |
| Dampak | Respons raksasa / endless stream dari upstream (atau dari proxy yang tidak dipercaya) mematikan proses bot lewat RAM atau disk. Tidak perlu akses khusus — cukup upstream mengembalikan body besar. |
| Fix minimum | Cek `Content-Length` > cap → abort. Saat streaming, hitung byte dan `break` bila lewat cap (mis. 30 MB). `timeout=(10, 60)` read-timeout eksplisit. |

---

## B. SEDANG — tambal sebelum deploy publik

### M-01. URL hasil scraping dipercaya tanpa validasi host/skema (SSRF blind + jalur tulis file)

| Item | Detail |
|---|---|
| Lokasi | `sources/alldatasheet.py:165`, `:244`, `:246`, `:257`; `sources/datasheet4u.py:96`, `:184` |
| Bukti | `full_url = "https:" + href if href.startswith("//") else href` — `href` mentah dari HTML. `pdf_url` diambil dari parameter `file=` sebuah `<iframe>` (`:246`) lalu langsung di-`session.get()`. `datasheet4u.py:96` sama: `f"{BASE_URL}{href}" if href.startswith("/") else href` → URL absolut apa pun diterima. Nol allowlist domain, nol validasi skema, nol penolakan IP privat. |
| Dampak | Content sumber/proxy residensial yang di-compromise bisa menyuntik `<iframe src="...file=https://169.254.169.254/latest/meta-data/">` → bot mengirim request ke host internal/metadata cloud dengan Referer-nya (blind SSRF; respons hanya dipakai kalau berawalan `%PDF-`). Jalur tulis file arbitrer terbuka bila penyerang memalsukan respons berawalan `%PDF-`. |
| Fix minimum | Allowlist host: `alldatasheet.com`, `datasheet4u.com` (+ subdomain), wajib `https://`. Tolak `href`/`file=` yang absolut. Resolve hostname, tolak RFC1918 / link-local / loopback sebelum request. |

### M-02. `.git.zip` (riwayat git penuh) ada di root proyek dan tidak di-`.gitignore`

| Item | Detail |
|---|---|
| Lokasi | `./.git.zip` (198 KB, 226 entry, permission `-rw-rw-r--`) |
| Bukti | `.gitignore` memuat `.env`, `proxies.txt`, `checkpoint.md` — **tidak** memuat `.git.zip`. File untracked tapi siap ikut ter-commit (`git add .`) / terkirim ke hosting / ter-share. |
| Dampak | Paket riwayat git memuat semua blob yang pernah di-commit, termasuk file yang sudah dihapus dari HEAD. Scan history saat ini bersih dari token, tapi satu commit berisi `.env` di masa depan = token bocor permanen lewat file ini. |
| Fix minimum | Tambah `.git.zip` (dan `*.zip`) ke `.gitignore`, atau pindahkan keluar repo. |

### M-03. Dua script bisa ditulis semua user lokal (mode 777)

| Item | Detail |
|---|---|
| Lokasi | `batch_download.py`, `batch_download_http.py` — `-rwxrwxrwx` |
| Bukti | `find . -perm -0002` → dua file itu. |
| Dampak | User lokal lain di mesin/VPS yang sama bisa menimpa script → eksekusi code sebagai user bot saat dijalankan. |
| Fix minimum | `chmod 755` (atau `644` + jalankan via `python3`). |

---

## C. RENDAH — hardening, bukan blocker

| ID | Temuan | Lokasi | Dampak | Fix |
|---|---|---|---|---|
| L-01 | `int(os.getenv("OWNER_ID","0"))` tanpa guard; `.env.example` berisi `OWNER_ID=your_discord_user_id_here` | `bots/discord/config.py:17`, `.env.example` | Copy-paste `.env.example` apa adanya → `ValueError` saat import, bot gagal start | Parse aman (`try/except` → 0) + komentar jelas di `.env.example` |
| L-02 | Detail exception dikirim ke user (`{e}`) | `purge_cog.py:64`, `datasheet_cog.py:444`, `panel_cog.py:194`, `:369` | Info disclosure: path internal, pesan library, topologi proxy | Log detail ke stdout, kirim pesan generik ke user |
| L-03 | View tombol tanpa `interaction_check` | `PackageSelectionView` (`datasheet_cog.py:297`), `DeleteFileSelect` (`panel_cog.py:160`), `RandomComponentView` (`random_cog.py:90`) | Aman **hanya karena** pesannya ephemeral. Kalau nanti pesan dijadikan publik, user lain bisa menekan tombol alur orang lain (IDOR/delegation) | Samakan pola dengan `CatalogPaginationView.interaction_check` (`datasheet_cog.py:178`) |
| L-04 | Konten pihak ketiga dirender langsung sebagai output bot (markdown/embed injection) | `datasheet_cog.py` (judul/manufacturer/description dari HTML), `random_cog.py` | Judul datasheet berisi `[Klik di sini](http://evil)` tampil sebagai tautan resmi bot → vektor phishing | `discord.utils.escape_markdown()` + strip URL pada field dari sumber |
| L-05 | Dependency tidak di-pin (`>=`) | `requirements.txt` | Build tidak reproducible; versi baru bisa memasukkan regresi/CVE tanpa sadar | Pin versi (`==`) atau pakai lockfile |
| L-06 | PDF dari pihak ketiga diparse in-process (pypdfium2/PDFium, native C++) | `core/specs_extractor.py:41`, `core/preview_extractor.py`, `core/pinout_extractor.py` | Kerentanan parser PDF = jalur RCE di proses bot; tanpa isolasi & tanpa cap ukuran | Jaga dependency PDF terbaru; jalankan ekstraksi di subprocess dengan limit memori/CPU + cap ukuran file |

Catatan tambahan (bukan celah, tapi bikin insiden tidak bisa dilacak): tidak ada log siapa meminta apa. Saat disk penuh/abuse terjadi, tidak ada bukti user mana penyebabnya.

---

## D. Yang sudah benar (jangan diubah)

- `.env` tidak pernah di-commit; `git ls-files` bersih; scan history semua branch: nol token/webhook.
- Tidak ada token/API key hardcoded di source (grep pola secret: nol hasil).
- Validasi magic byte `%PDF-` sebelum file disimpan/dikirim (`alldatasheet.py`, `datasheet4u.py`) — sudah menahan respons HTML/Cloudflare palsu.
- Sanitasi nama file untuk path traversal sudah benar (`sanitize_part_no` membuang `/`, `\`, `:` dan men-`strip('_')`) + ada unit test (`tests/test_batch_http.py`).
- `/purge` sudah pakai `@app_commands.checks.has_permissions(manage_messages=True)` + clamp 1..100.
- `/panel` sudah owner-gated (env `OWNER_ID`, fallback `application_info().owner`) + `interaction_check` di view.
- Kredensial proxy di-mask saat logging (`next_proxy.split('@')[-1]`).
- Bot pakai `Intents.default()` (tanpa `message_content`) — permukaan minimal.

---

## E. Urutan patch yang disarankan

1. **H-01** cooldown + auto-prune cache — mencegah bot mati, effort paling kecil.
2. **H-02** cap ukuran unduhan (Content-Length + byte counter saat streaming).
3. **M-01** allowlist host + tolak URL absolut/IP privat di kedua adapter.
4. **M-02/M-03** `.gitignore` + `chmod 755`.
5. **L-01..L-06** hardening bertahap.

Eksekusi **SELESAI** 2026-11-24 (semua temuan dipatch, urutan TINGGI → SEDANG → RENDAH).

---

## F. Status patch & hasil pengujian

Semua temuan sudah dipatch dan diuji. Verifikasi: `venv/bin/python tests/test_security_patches.py` → **13/13 PASS**, `venv/bin/python tests/test_batch_http.py` → **29/29 PASS**, `py_compile` 15 file → OK, smoke-load 9 cog + 9 command → OK.

| ID | Patch | Bukti uji |
|----|-------|-----------|
| H-01 | cooldown `/datasheet` 1/120s, `/pinout` 1/120s, `/random` 1/30s; `prune_cache()` per-invocation + `setup_hook`; kuota disk `MAX_TOTAL_MB` (default 5000) di CLI batch | `cmd.checks` non-kosong untuk 3 command; `folder_size_mb()` akurat |
| H-02 | `core/pdf_fetch.py`: `MAX_PDF_BYTES` 30MB, `MAX_PARSE_BYTES` 40MB, `MIN_PDF_BYTES` 2048; `content_length_exceeds()` + `read_capped()`/`write_capped()` di kedua adapter | unduh live NE555 2.19MB & LM358 2.08MB sukses, header `%PDF-`, trailer `%%EOF`; `write_capped` hapus file saat lewat batas |
| M-01 | `ALLOWED_HOSTS` + `is_allowed_url()` (https-only, suffix-match, tolak IP/URL privat) di `alldatasheet.py` & `datasheet4u.py` | 8 payload jahat (`evil.com`, `alldatasheet.com.evil.com`, `169.254.169.254`, `127.0.0.1`, `//host`, http) ditolak; `download_single` dengan `pdf_url` jahat → `None`, nol file tertulis |
| M-02 | `.gitignore` + `.git.zip`, `*.zip` | `git check-ignore -v .git.zip` cocok |
| M-03 | `chmod 755` `batch_download.py`, `batch_download_http.py` | mode world-writable hilang |
| L-01 | `_int_env()` untuk `OWNER_ID` + `MAX_FILE_SIZE_MB` | nilai ENV non-numerik jatuh ke default, tidak crash |
| L-02 | exception tidak lagi bocor ke user (`purge_cog`, `panel_cog`, `datasheet_cog`) — detail hanya ke log server | compile + smoke load OK |
| L-03 | `interaction_check` + `on_error` di semua View (`PackageSelectionView`, `CatalogPaginationView`, `RandomComponentView`, `OwnerOnlyView` untuk `/panel`) | cek atribut kelas PASS |
| L-04 | `_safe_text()`: escape markdown + ganti URL jadi `[tautan]` + clamp panjang untuk semua field pihak ketiga | URL & `**bold**` hilang dari output, clamp 100 char terverifikasi |
| L-05 | `requirements.txt` di-pin ke versi terpasang | — |
| L-06 | `too_large_to_parse()` dipakai `specs_extractor`, `preview_extractor`, `pinout_extractor` | PDF > 40MB → `{}` / `None`; PDF normal 2.19MB tetap menghasilkan 3 spec + thumbnail + pinout |

Catatan: isolasi parser PDF ke subprocess (bagian berat L-06) **tidak** dikerjakan — butuh arsitektur worker terpisah. Batas ukuran sudah menutup vektor OOM praktis. `ponytail:` upgrade path = jalankan `pypdfium2` di `multiprocessing` bila perlu isolasi penuh.
