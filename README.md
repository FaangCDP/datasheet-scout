# 🔍 Datasheet Scout

A high-performance electronic component datasheet scraper, downloader, and modular Discord bot with automated multi-source fallback (`datasheet4u.com` & `alldatasheet.com`), Cloudflare WAF bypass, pinout diagram extraction, and interactive Discord UI.

> **Note**: This is an experimental hobby project built for electronics tinkering and learning. Fully implemented by AI coding agents under human direction and prompt orchestration ("mandor").

---

## ⚡ Features

### 1. Multi-Source Scraping Engine
- **Automated Fallback**: Primary search on `datasheet4u.com`. If no matches or low relevance scores are found, automatically failovers to `alldatasheet.com`.
- **Cloudflare TLS Fingerprint Mitigation**: Employs `curl_cffi` browser impersonation (`chrome124`) to handle automated Cloudflare TLS fingerprint checks on `alldatasheet.com`. *(Note: Mitigates passive bot detection headers; does not solve interactive Turnstile or CAPTCHA interstitials if triggered by aggressive rate limits).*
- **Intelligent Relevance Ranking**: Strips package suffixes (e.g., `LM358D` → `LM358`) to query clean base part numbers, scoring search results to prioritize exact matches (e.g., distinguishing `Arduino Uno` from `Arduino Nano`).
- **File Integrity & Safety**: Sanitizes filename path separators to prevent directory traversal exploits. Validates binary magic bytes (`%PDF-`), minimum file sizes, dummy error banners (25.3 KB placeholder error PDFs), and trailer markers (`%%EOF`) to reject corrupted or truncated downloads. *(Note: Structural checks ensure valid PDF payloads, though users should still inspect component revisions for second-source variations).*

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
- **`/purge [jumlah]`**: Deletes recent messages with a self-destructing 5-second confirmation notice.
- **`/info`**: System runtime and local datasheet cache statistics.
- **`/myid`**: Instant user ID display for configuring `OWNER_ID` in `.env`.
- **`/help`**: Interactive command reference.

### 3. Standalone CLI Tool
- **`batch_download.py`**: Interactive CLI for manual component input (comma-separated for multi-part downloads).

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
├── tests/                       # Automated test suites (43 test cases)
│   ├── test_batch_http.py       # 29 tests: sanitization, file parser, PDF header checks
│   └── test_core_and_bot.py     # 14 tests: package classifier, specs regex, pinout heuristics, bot cogs
├── .env.example                 # Environment variables template
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
Copy `.env.example` to `.env` and fill in your values:
```bash
cp .env.example .env
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

### Running CLI Downloader
```bash
python batch_download.py
```

### Running Test Suite
```bash
# Run all 43 automated unit & module tests:
python -m unittest discover tests -v
```

---

## 📄 License & Disclaimer
This is an open hobbyist project. Datasheets and trademarks are intellectual properties of their respective semiconductor manufacturers.
