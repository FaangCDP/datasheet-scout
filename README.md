# 🔍 Datasheet Scout

A high-performance electronic component datasheet scraper, batch downloader, and modular Discord bot with automated multi-source fallback (`datasheet4u.com` & `alldatasheet.com`), Cloudflare WAF bypass, pinout diagram extraction, and interactive Discord UI.

---

## ⚡ Features

### 1. Multi-Source Scraping Engine
- **Automated Fallback**: Primary search on `datasheet4u.com`. If no matches or low relevance scores are found, automatically failover to `alldatasheet.com`.
- **Cloudflare TLS Fingerprint Bypass**: Employs `curl_cffi` browser impersonation (`chrome124`) to navigate Cloudflare bot-management walls without manual intervention.
- **Intelligent Relevance Ranking**: Strips package suffixes (e.g., `LM358D` → `LM358`) to query clean base part numbers, scoring search results to prioritize exact matches (e.g., distinguishing `Arduino Uno` from `Arduino Nano`).
- **File Integrity & Safety**: Sanitizes filename path separators to prevent path traversal errors and verifies binary magic bytes (`%PDF-`) to reject fake HTML/challenge response payloads.

### 2. Discord Bot (Slash Commands & Modular Architecture)
Built with `discord.py` using a strict **1 Command = 1 File Cog** pattern and automatic cog discovery:
- **`/datasheet <komponen> [kemasan] [pilihan_kemasan] [jumlah] [file]`**:
  - Direct PDF attachment delivery (< 25 MB) with cover preview thumbnail.
  - **In-memory Autocomplete**: Instant suggestions (< 10 ms) for popular microcontrollers, op-amps, logic ICs, and regulators.
  - **Interactive Package Buttons (`pilihan_kemasan: True`)**: Presents button choices for distinct physical packages (`DIP`, `SOIC`, `TSSOP`, `QFN`, etc.) before downloading to conserve server disk space.
  - **Batch Attachment**: Accepts `.txt` files (1 part per line) and bundles multiple datasheets into `.zip` archives.
  - **Key Specs Card**: Automatically extracts operating voltage, clock frequency, package types, and temperature range directly onto Discord Embeds.
- **`/pinout <komponen>`**:
  - Automatically scans PDF pages for pin configuration/layout sections.
  - Renders and sends high-resolution pinout diagram images directly in chat.
- **`/panel` (Owner-Only Server Dashboard)**:
  - Real-time VPS resource monitor (CPU load, RAM usage, Disk space).
  - Live latency tracking for Discord gateway and provider health checks.
  - Interactive disk inspector dropdown to delete selected PDF files.
  - One-click cache cleanup for temporary thumbnails and pinout images.
  - One-click live slash command tree sync (`tree.sync()`).
  - Auto-refreshes every 1 minute with a 15-minute active session timeout.
- **`/ping`**: Gateway latency check in milliseconds.
- **`/purge [jumlah]`**: Deletes up to 100 recent messages with a self-destructing 5-second confirmation notice.
- **`/info`**: System runtime and local datasheet cache statistics.
- **`/myid`**: Instant user ID display for configuring `.env`.
- **`/help`**: Interactive command reference.

### 3. Standalone CLI Tools
- **`batch_download.py`**: Interactive CLI for manual component input (comma-separated for multi-part downloads).
- **`batch_download_http.py`**: Automated batch downloader reading category files from `list/*.txt` with `--count` and `--yes` CLI flags.

---

## 📁 Project Structure

```text
├── sources/                     # Individual provider scraper modules
│   ├── __init__.py
│   ├── datasheet4u.py           # Provider implementation for datasheet4u.com
│   └── alldatasheet.py          # Provider implementation for alldatasheet.com
├── core/                        # Core business logic and standalone tools
│   ├── __init__.py
│   ├── scraper.py               # Scraper orchestrator and multi-source facade
│   ├── package_classifier.py    # Suffix stripping and distinct package grouping
│   ├── preview_extractor.py     # PDF cover thumbnail generator (via pdftoppm)
│   ├── specs_extractor.py       # Key specification parser (via pdftotext)
│   └── pinout_extractor.py      # Pinout diagram detector and renderer
├── bots/
│   └── discord/
│       ├── __init__.py
│       ├── config.py            # Environment configuration loader
│       ├── bot.py               # Main bot client with auto-discovery setup
│       ├── .env.example         # Environment template
│       └── cogs/                # Modular 1-file-per-command slash commands
│           ├── __init__.py
│           ├── datasheet_cog.py # /datasheet command & interactive views
│           ├── pinout_cog.py    # /pinout command
│           ├── panel_cog.py     # /panel owner dashboard
│           ├── myid_cog.py      # /myid command
│           ├── help_cog.py      # /help guide
│           ├── info_cog.py      # /info status
│           ├── ping_cog.py      # /ping latency
│           └── purge_cog.py     # /purge channel cleaner
├── batch_download.py            # CLI: manual input mode
├── batch_download_http.py       # CLI: list/*.txt automated mode
├── list/                        # Component list definitions (e.g. Microcontroller.txt)
├── tests/                       # Unit tests
│   └── test_batch_http.py       # 29 test cases covering sanitization, parser, PDF checks
├── requirements.txt             # Python package dependencies
└── .gitignore                   # Ignores .env, venv/, downloads/, cache images
```

---

## 🛠️ Prerequisites & Installation

### 1. System Requirements
- Linux / macOS / Windows
- Python 3.10+
- `poppler-utils` (provides `pdftotext`, `pdftoppm`, and `pdfinfo`):
  ```bash
  # Debian / Ubuntu / Linux Mint
  sudo apt install poppler-utils

  # macOS
  brew install poppler

  # Arch Linux
  sudo pacman -S poppler
  ```

### 2. Clone and Setup Environment
```bash
git clone https://github.com/FaangCDP/datasheet-scout.git
cd datasheet-scout

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Variables
Copy the template and configure your Discord credentials:
```bash
cp bots/discord/.env.example .env
```
Edit `.env`:
```env
DISCORD_TOKEN=your_discord_bot_token_here
OWNER_ID=your_discord_user_id_here
MAX_FILE_SIZE_MB=25
```

---

## 🚀 Usage

### Running the Discord Bot
```bash
python -m bots.discord.bot
```

### Running CLI Batch Downloaders
```bash
# Interactive manual input:
python batch_download.py

# Automated list download from list/ directory:
python batch_download_http.py --count 1 --yes
```

### Running Test Suite
```bash
python -m unittest tests.test_batch_http -v
```

---

## 📄 License
This project is for educational and hobbyist electronics practical work. Datasheets are intellectual properties of their respective semiconductor manufacturers.
