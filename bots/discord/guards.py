"""
bots/discord/guards.py -- Guard anti-abuse bersama untuk seluruh cog.

1. handle_cooldown(): pesan seragam saat pengguna terkena rate limit command.
2. prune_cache(): buang cache PDF kedaluwarsa/berlebih agar disk VPS tidak penuh.

Kuota diatur via ENV: MAX_CACHE_MB (default 500), MAX_CACHE_AGE_HOURS (default 72).
"""

import os
import time

import discord
from discord import app_commands

from bots.discord import config

MAX_CACHE_MB = int(os.getenv("MAX_CACHE_MB", "500"))
MAX_CACHE_AGE_HOURS = int(os.getenv("MAX_CACHE_AGE_HOURS", "72"))
PRUNE_MIN_INTERVAL_S = 300   # jangan pindai disk pada setiap request
FRESH_FILE_GRACE_S = 600     # berkas yang baru dibuat tidak ikut dibuang oleh kuota

_last_prune = 0.0


def prune_cache(force: bool = False) -> tuple[int, int]:
    """Hapus PDF cache yang melewati batas usia, lalu sisakan total <= MAX_CACHE_MB.

    Returns:
        tuple (jumlah_file_dihapus, byte_dibebaskan)
    """
    global _last_prune
    now = time.time()
    if not force and now - _last_prune < PRUNE_MIN_INTERVAL_S:
        return 0, 0
    _last_prune = now

    root_dir = config.DOWNLOAD_DIR
    if not os.path.isdir(root_dir):
        return 0, 0

    entries = []
    for root, _, files in os.walk(root_dir):
        for name in files:
            if not name.lower().endswith(".pdf"):
                continue
            path = os.path.join(root, name)
            try:
                st = os.stat(path)
            except OSError:
                continue
            entries.append((st.st_mtime, st.st_size, path))

    deleted = 0
    freed = 0
    survivors = []

    # 1. Buang berkas yang lebih tua dari batas usia
    max_age = MAX_CACHE_AGE_HOURS * 3600
    for mtime, size, path in entries:
        if max_age > 0 and now - mtime > max_age and _unlink(path):
            deleted += 1
            freed += size
        else:
            survivors.append((mtime, size, path))

    # 2. Jika total masih melebihi kuota, buang yang paling tua lebih dulu
    total = sum(size for _, size, _ in survivors)
    limit = MAX_CACHE_MB * 1024 * 1024
    if limit > 0 and total > limit:
        for mtime, size, path in sorted(survivors):
            if total <= limit:
                break
            if now - mtime < FRESH_FILE_GRACE_S:
                continue
            if _unlink(path):
                deleted += 1
                freed += size
                total -= size

    if deleted:
        print(f"[cache] prune: {deleted} file PDF dihapus, {freed / (1024 * 1024):.2f} MB dibebaskan.")
    return deleted, freed


def _unlink(path: str) -> bool:
    try:
        os.remove(path)
        return True
    except OSError:
        return False


async def handle_cooldown(interaction: discord.Interaction, error: Exception) -> bool:
    """Kirim sisa waktu tunggu bila error adalah CommandOnCooldown. True jika ditangani."""
    if not isinstance(error, app_commands.CommandOnCooldown):
        return False
    msg = f"⏳ Terlalu banyak permintaan. Coba lagi dalam {error.retry_after:.0f} detik."
    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)
    return True
