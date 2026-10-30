"""
bots/discord/cogs/purge_cog.py -- Slash Command: /purge
Membersihkan pesan di channel:
- parameter jumlah bersifat opsional (default = 10 pesan).
- pesan konfirmasi otomatis terhapus dalam 5 detik agar channel tetap bersih.
"""

import asyncio
import discord
from discord import app_commands
from discord.ext import commands


class PurgeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="purge",
        description="Hapus pesan di channel ini (otomatis atau sesuai jumlah yang ditentukan)"
    )
    @app_commands.describe(
        jumlah="Jumlah pesan yang ingin dihapus (Opsional, default: 10 pesan, maks: 100)"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction, jumlah: int = 10):
        # Validasi batas jumlah
        if jumlah < 1:
            await interaction.response.send_message(
                "⚠️ Jumlah pesan minimal yang dihapus adalah 1.",
                ephemeral=True
            )
            return

        if jumlah > 100:
            jumlah = 100

        # Beri respon awal singkat
        await interaction.response.defer(ephemeral=False)

        try:
            # Hapus pesan (limit + 1 untuk menghapus interaksi awal jika ada)
            deleted = await interaction.channel.purge(limit=jumlah)
            
            # Kirim pesan konfirmasi publik
            confirm_msg = await interaction.channel.send(
                f"🧹 Berhasil menghapus **{len(deleted)}** pesan. *(Pesan ini otomatis hilang dalam 5 detik)*"
            )

            # Tunggu 5 detik lalu hapus pesan konfirmasi agar chat bersih
            await asyncio.sleep(5)
            try:
                await confirm_msg.delete()
            except discord.NotFound:
                pass

        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Bot tidak memiliki izin `Manage Messages` di channel ini.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Terjadi kesalahan saat menghapus pesan: {e}",
                ephemeral=True
            )

    @purge.error
    async def purge_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            msg = "❌ Anda memerlukan izin `Manage Messages` untuk menggunakan perintah ini."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(PurgeCog(bot))
