"""
bots/discord/cogs/help_cog.py -- Slash Command: /help
"""

import discord
from discord import app_commands
from discord.ext import commands


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="help",
        description="Panduan penggunaan seluruh perintah slash pada bot"
    )
    async def help_command(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📖 Panduan Perintah Bot Datasheet",
            description="Daftar perintah slash (`/`) yang tersedia pada bot ini:",
            color=discord.Color.gold()
        )

        embed.add_field(
            name="📄 `/datasheet <komponen> [kemasan] [pilihan_kemasan] [jumlah] [file]`",
            value=(
                "Mencari & mengunduh datasheet komponen elektronik dalam format PDF.\n"
                "• **komponen** *(Wajib)*: Masukkan nama komponen (contoh: `/datasheet komponen:NE555`).\n"
                "• **kemasan** *(Opsional)*: Filter langsung ke bentuk fisik tertentu (contoh: `DIP`, `SOIC`).\n"
                "• **pilihan_kemasan** *(Opsional, True/False)*: Tampilkan tombol interaktif untuk memilih kemasan (DIP, SOIC, TSSOP, dll.) sebelum mengunduh agar hemat ruang.\n"
                "• **jumlah** *(Opsional, default 1)*: Jumlah varian datasheet yang ingin diunduh.\n"
                "• **file** *(Opsional)*: Lampirkan file `.txt` berisi daftar komponen tambahan untuk unduhan batch."
            ),
            inline=False
        )

        embed.add_field(
            name="🔌 `/pinout <komponen>`",
            value="Mengekstrak diagram susunan kaki komponen dan mengirimkannya ke DM pribadi Anda (privat & bersih).",
            inline=False
        )

        embed.add_field(
            name="🎲 `/random`",
            value="Mengundi komponen elektronik secara acak untuk ide proyek atau belajar praktikum elektronika.",
            inline=False
        )

        embed.add_field(
            name="🏓 `/ping`",
            value="Mengecek koneksi bot dan mengukur latensi gateway Discord dalam milidetik (ms).",
            inline=False
        )

        embed.add_field(
            name="🧹 `/purge [jumlah]`",
            value=(
                "Menghapus pesan terbaru di channel aktif (default 10 pesan, maks 100).\n"
                "Pesan konfirmasi otomatis terhapus dalam 5 detik. *(Memerlukan izin Manage Messages)*."
            ),
            inline=False
        )

        embed.add_field(
            name="ℹ️ `/info`",
            value="Menampilkan status teknis bot, direktori cache, dan spesifikasi runtime.",
            inline=False
        )

        embed.add_field(
            name="🆔 `/myid`",
            value="Melihat User ID Discord Anda secara instan untuk disalin ke file `.env`.",
            inline=False
        )

        embed.set_footer(text="Datasheet Bot • Sumber: datasheet4u.com & alldatasheet.com")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
