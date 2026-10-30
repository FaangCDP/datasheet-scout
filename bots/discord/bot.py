"""
bots/discord/bot.py -- Main Entry Point Bot Discord (Slash Commands Only)
"""

import asyncio
import sys
from pathlib import Path
import discord
from discord.ext import commands

# Tambahkan root proyek ke sys.path agar import 'core' dan 'bots' berjalan mulus
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bots.discord import config


class DatasheetBot(commands.Bot):
    def __init__(self):
        # Intents default sudah mencukupi untuk slash commands murni
        intents = discord.Intents.default()
        super().__init__(command_prefix=[], intents=intents)

    async def setup_hook(self):
        # Auto-discover dan muat setiap file cog secara modular (1 file = 1 command)
        cogs_dir = Path(__file__).resolve().parent / "cogs"
        for cog_file in sorted(cogs_dir.glob("*_cog.py")):
            extension_name = f"bots.discord.cogs.{cog_file.stem}"
            try:
                await self.load_extension(extension_name)
                print(f"[+] Loaded cog: {cog_file.name}")
            except Exception as e:
                print(f"[ERROR] Gagal memuat cog {cog_file.name}: {e}")

        # Sync slash commands secara global ke Discord API
        try:
            synced = await self.tree.sync()
            print(f"[+] Berhasil sinkronisasi {len(synced)} slash command(s).")
        except Exception as e:
            print(f"[ERROR] Gagal sinkronisasi slash command: {e}")

    async def on_ready(self):
        print(f"[+] Bot Discord siap & terhubung sebagai: {self.user} (ID: {self.user.id})")
        print(f"[i] Perintah tersedia: /datasheet, /ping, /purge, /help, /info")


def run():
    if not config.DISCORD_TOKEN:
        print("\n" + "=" * 60)
        print("  [ERROR] DISCORD_TOKEN belum diatur!")
        print("  Silakan isi token bot Anda di file .env:")
        print("  DISCORD_TOKEN=your_bot_token_here")
        print("=" * 60 + "\n")
        sys.exit(1)

    bot = DatasheetBot()
    bot.run(config.DISCORD_TOKEN)


if __name__ == "__main__":
    run()
