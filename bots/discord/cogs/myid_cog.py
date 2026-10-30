"""
bots/discord/cogs/myid_cog.py -- Slash Command: /myid
Menampilkan ID akun Discord pengguna secara instan dan sederhana.
"""

import discord
from discord import app_commands
from discord.ext import commands


class MyIdCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="myid",
        description="Lihat ID akun Discord Anda secara instan"
    )
    async def myid(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        await interaction.response.send_message(
            f"DiscordID: `{user_id}`",
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(MyIdCog(bot))
