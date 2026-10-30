"""
bots/discord/cogs/info_cog.py -- Slash Command: /info
"""

import os
import sys
import time
import discord
from discord import app_commands
from discord.ext import commands
from bots.discord import config


class InfoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.start_time = time.time()

    @app_commands.command(
        name="info",
        description="Menampilkan status teknis bot dan statistik penyimpanan"
    )
    async def info_command(self, interaction: discord.Interaction):
        uptime_sec = int(time.time() - self.start_time)
        hrs = uptime_sec // 3600
        mins = (uptime_sec % 3600) // 60
        secs = uptime_sec % 60
        uptime_str = f"{hrs}j {mins}m {secs}s" if hrs > 0 else f"{mins}m {secs}s"

        # Hitung statistik folder cache downloads
        cached_count = 0
        total_cache_bytes = 0
        if os.path.isdir(config.DOWNLOAD_DIR):
            for root, _, files in os.walk(config.DOWNLOAD_DIR):
                for f in files:
                    if f.lower().endswith(".pdf"):
                        cached_count += 1
                        try:
                            total_cache_bytes += os.path.getsize(os.path.join(root, f))
                        except OSError:
                            pass

        total_cache_mb = total_cache_bytes / (1024 * 1024)

        embed = discord.Embed(
            title="ℹ️ Informasi Sistem & Status Bot",
            color=discord.Color.teal()
        )
        embed.add_field(name="Status Bot", value="🟢 Online / Ready", inline=True)
        embed.add_field(name="Uptime Sesi", value=uptime_str, inline=True)
        embed.add_field(name="Latensi Bot", value=f"{round(self.bot.latency * 1000)} ms", inline=True)

        embed.add_field(
            name="Lingkungan Runtime",
            value=f"• Python: `{sys.version.split()[0]}`\n• discord.py: `{discord.__version__}`",
            inline=True
        )
        embed.add_field(
            name="Cache Datasheet Lokal",
            value=f"• Berkas PDF: `{cached_count} file`\n• Total Ukuran: `{total_cache_mb:.1f} MB`",
            inline=True
        )
        embed.add_field(
            name="Database Sumber Aktif",
            value=(
                "• [datasheet4u.com](https://datasheet4u.com) *(900.000+ Komponen)*\n"
                "• [alldatasheet.com](https://www.alldatasheet.com) *(100.000.000+ Komponen)*"
            ),
            inline=False
        )

        embed.set_footer(text=f"Bot ID: {self.bot.user.id if self.bot.user else 'Unknown'}")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(InfoCog(bot))
