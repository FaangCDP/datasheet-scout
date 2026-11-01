"""
bots/discord/cogs/pinout_cog.py -- Slash Command: /pinout
Menampilkan diagram susunan kaki/koneksi komponen elektronik langsung sebagai gambar.
"""

import asyncio
import os
import discord
from discord import app_commands
from discord.ext import commands

from core.scraper import (
    create_session,
    search_component,
    download_single,
    sanitize_filename,
)
from core.pinout_extractor import extract_pinout_image
from bots.discord import config
from bots.discord.cogs.datasheet_cog import COMMON_COMPONENTS


class PinoutCog(commands.Cog):
    """Cog slash command untuk menampilkan gambar diagram susunan pin/kaki komponen."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = create_session()

    @app_commands.command(
        name="pinout",
        description="Tampilkan gambar diagram susunan kaki/koneksi komponen elektronik"
    )
    @app_commands.describe(
        komponen="Nama komponen yang ingin dilihat diagram kakinya (contoh: NE555, LM358, Arduino Uno)"
    )
    async def pinout(self, interaction: discord.Interaction, komponen: str):
        comp_name = komponen.strip()
        if not comp_name:
            await interaction.response.send_message(
                "⚠️ Nama komponen wajib diisi dan tidak boleh kosong.",
                ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True, ephemeral=True)

        # 1. Cari komponen di database
        results = await asyncio.to_thread(search_component, self.session, comp_name, 1)
        if not results:
            await interaction.followup.send(
                f"❌ Komponen **{comp_name}** tidak ditemukan di database.",
                ephemeral=True
            )
            return

        res = results[0]
        part_no = res.get("part_no", comp_name)
        mfr = res.get("manufacturer", "Unknown")
        source = res.get("source", "datasheet4u")
        detail_url = res.get("url", "")

        # 2. Periksa apakah PDF sudah ada di cache lokal atau unduh jika belum
        filename = sanitize_filename(part_no, mfr, source=source)
        expected_file = os.path.join(config.DOWNLOAD_DIR, filename)

        is_cached = (
            os.path.isfile(expected_file)
            and os.path.getsize(expected_file) > 1000
            and os.path.getsize(expected_file) != 25307
        )
        if is_cached:
            file_path = expected_file
        else:
            file_path = await asyncio.to_thread(
                download_single, self.session, res, 1, config.DOWNLOAD_DIR
            )

        if not file_path or not os.path.isfile(file_path):
            await interaction.followup.send(
                f"⚠️ Berhasil menemukan **{part_no} ({mfr})**, tetapi berkas PDF tidak dapat diakses.",
                ephemeral=True
            )
            return

        # 3. Ekstrak halaman gambar pinout
        img_path, page_num = await asyncio.to_thread(extract_pinout_image, file_path)

        if not img_path or not os.path.isfile(img_path):
            await interaction.followup.send(
                f"⚠️ Diagram susunan kaki tidak dapat diekstrak otomatis dari PDF **{part_no}**.\n"
                f"Silakan unduh dokumen lengkapnya melalui `/datasheet komponen:{comp_name}`.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"🔌 Diagram Pinout: {part_no}",
            description=f"Susunan kaki komponen dari pabrikan **{mfr}** (Halaman `{page_num}`).",
            url=detail_url,
            color=discord.Color.orange()
        )
        embed.set_image(url="attachment://pinout.png")
        embed.set_footer(text=f"Sumber: {source}.com • Gunakan /datasheet untuk PDF lengkap")

        # Coba kirim via DM (Direct Message) terlebih dahulu
        sent_to_dm = False
        discord_img = discord.File(img_path, filename="pinout.png")

        try:
            await interaction.user.send(embed=embed, file=discord_img)
            sent_to_dm = True
            await interaction.followup.send(
                f"📬 Diagram pinout untuk **{part_no}** telah dikirim langsung ke **DM (Pesan Pribadi)** Anda!",
                ephemeral=True
            )
        except (discord.Forbidden, discord.HTTPException):
            # Fallback jika DM pengguna ditutup/dikunci: kirim di server secara ephemeral
            discord_img_fallback = discord.File(img_path, filename="pinout.png")
            await interaction.followup.send(
                content="⚠️ *Pesan Pribadi (DM) Anda terkunci. Menampilkan diagram secara privat di sini:*",
                embed=embed,
                file=discord_img_fallback,
                ephemeral=True
            )

        # Auto-clean: Hapus file gambar diagram pinout lokal setelah berhasil diunggah ke Discord CDN
        try:
            if img_path and os.path.isfile(img_path):
                os.remove(img_path)
        except OSError:
            pass

    @pinout.autocomplete('komponen')
    async def pinout_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete nama komponen untuk perintah /pinout."""
        catalog = set(COMMON_COMPONENTS)

        # Sertakan komponen dari folder downloads/
        if os.path.isdir(config.DOWNLOAD_DIR):
            for root, _, files in os.walk(config.DOWNLOAD_DIR):
                for f in files:
                    if f.endswith(".pdf") and "_" in f:
                        part = f.split("_")[0]
                        if len(part) >= 2 and not part.startswith("."):
                            catalog.add(part)

        cur = current.strip().lower()
        if not cur:
            suggestions = sorted(catalog)[:25]
        else:
            starts = [c for c in sorted(catalog) if c.lower().startswith(cur)]
            contains = [c for c in sorted(catalog) if cur in c.lower() and c not in starts]
            suggestions = (starts + contains)[:25]

        return [app_commands.Choice(name=name, value=name) for name in suggestions]


async def setup(bot: commands.Bot):
    await bot.add_cog(PinoutCog(bot))
