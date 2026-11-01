"""
bots/discord/config.py -- Konfigurasi Bot Discord
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Cari file .env di bots/discord/ atau di root proyek
env_path = Path(__file__).resolve().parent / ".env"
if not env_path.exists():
    env_path = Path(__file__).resolve().parents[2] / ".env"

load_dotenv(dotenv_path=env_path)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
DOWNLOAD_DIR = os.getenv(
    "DOWNLOAD_DIR",
    str(Path(__file__).resolve().parents[2] / "downloads")
)
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "25"))
ALLDATASHEET_PROXY = os.getenv("ALLDATASHEET_PROXY", "").strip()
