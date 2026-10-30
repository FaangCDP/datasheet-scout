"""
bots/discord/cogs/ping_cog.py -- Slash Command: /ping
"""

import discord
from discord import app_commands
from discord.ext import commands


class PingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="ping",
        description="Periksa status koneksi dan latensi bot"
    )
    async def ping(self, interaction: discord.Interaction):
        latency_ms = round(self.bot.latency * 1000)
        await interaction.response.send_message(
            f"🏓 **Pong!** Latensi bot: `{latency_ms}ms`",
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(PingCog(bot))
