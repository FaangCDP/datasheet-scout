"""
bots/discord/cogs/random_cog.py -- Slash Command: /random

Mengambil dan menyajikan 1 komponen elektronik secara acak dari database komponen.
Menampilkan ringkasan fungsi, kategori, serta tombol aksi cepat untuk mengunduh datasheet atau pinout.
Semua interaksi bersifat Ephemeral dan file dikirimkan ke DM.
"""

import random
import discord
from discord import app_commands
from discord.ext import commands

RANDOM_CURATED_COMPONENTS = [
    {
        "part_no": "NE555",
        "category": "Timer / Oscillator IC",
        "desc": "IC pewaktu presisi legendaris yang mampu menghasilkan delay waktu atau osilasi gelombang kotak (astable/monostable) hingga ratusan kHz.",
        "common_uses": "Pewaktu lampu sein, generator sinyal PWM, sirine audio, sensor sentuh.",
    },
    {
        "part_no": "LM358",
        "category": "Dual Operational Amplifier (Op-Amp)",
        "desc": "Op-Amp ganda berdaya rendah dengan rentang tegangan catu daya tunggal luas (3V - 32V), dirancang khusus untuk rangkaian analog sensitif.",
        "common_uses": "Penguat sinyal sensor, komparator tegangan, filter audio aktif, detektor sinyal kecil.",
    },
    {
        "part_no": "ATmega328P",
        "category": "8-Bit AVR Microcontroller",
        "desc": "Mikrokontroler inti pada Arduino Uno/Nano dengan memori flash 32KB, 2KB SRAM, 1KB EEPROM, dan 23 jalur I/O yang fleksibel.",
        "common_uses": "Otomasi rumah, robotika dasar, modul kendali sensor praktikum, sistem instrumentasi.",
    },
    {
        "part_no": "ESP32",
        "category": "Dual-Core Wi-Fi & Bluetooth SoC",
        "desc": "System-on-Chip performa tinggi bertenaga Xtensa LX6 32-bit (240MHz) dengan antena Wi-Fi 2.4GHz dan BLE terintegrasi.",
        "common_uses": "Proyek IoT (Internet of Things), web server mandiri, kendali smart home nirkabel, sensor logger.",
    },
    {
        "part_no": "74HC595",
        "category": "8-Bit Serial-in/Parallel-out Shift Register",
        "desc": "IC ekspansi pin output digital dengan latch internal, memungkinkan mikrokontroler mengontrol 8 pin beban hanya dengan 3 pin sinyal.",
        "common_uses": "Kendali display 7-segment bertingkat, matriks LED 8x8, penambahan relay/output mikrokontroler.",
    },
    {
        "part_no": "LM7805",
        "category": "Linear Voltage Regulator (5V)",
        "desc": "Regulator penurun tegangan linier dengan proteksi batas arus internal dan shutdown termal, menghasilkan tegangan stabil presisi +5V hingga arus 1.5A.",
        "common_uses": "Catu daya logika digital 5V dari baterai 9V/12V, stabilisator tegangan mikrokontroler.",
    },
    {
        "part_no": "IRFZ44N",
        "category": "N-Channel Power MOSFET",
        "desc": "Transistor daya medan (MOSFET) dengan resistansi on ultra rendah (RDS(on) 17.5 mOhm) mampu mengalirkan arus hingga 49A pada 55V.",
        "common_uses": "Sakelar driver motor DC torsi tinggi, pengendali lampu daya besar, inverter DC-to-AC.",
    },
    {
        "part_no": "BC547",
        "category": "NPN General Purpose BJT",
        "desc": "Transistor bipolar NPN serbaguna dengan penguatan arus (hFE) tinggi hingga 800, standar utama dalam laboratorium elektronika dasar.",
        "common_uses": "Driver relay kecil, sakelar logika sederhana, penguat sinyal audio awal (pre-amp).",
    },
    {
        "part_no": "CD4017",
        "category": "Decade Counter / Divider IC",
        "desc": "IC pencacah dekade CMOS dengan 10 output decoding individual. Setiap pulsa clock menggeser logika HIGH dari pin 0 sampai pin 9 berurutan.",
        "common_uses": "Lampu LED berjalan (running LED/chaser), sequencer nada audio, pembagi frekuensi pulsa.",
    },
    {
        "part_no": "DS3231",
        "category": "Extremely Accurate I2C-Integrated RTC",
        "desc": "Real-Time Clock berpresisi sangat tinggi dengan kristal osilator dan sensor kompensasi suhu (TCXO) internal.",
        "common_uses": "Jam digital presisi tanpa koneksi internet, data logging dengan stempel waktu akurat.",
    },
    {
        "part_no": "AMS1117-3.3",
        "category": "Low Dropout (LDO) Linear Regulator",
        "desc": "Regulator LDO efisien yang menurunkan tegangan 5V ke 3.3V dengan stabil hingga arus 1A untuk komponen logika modern.",
        "common_uses": "Catu daya modul ESP8266, ESP32, Raspberry Pi Pico, kartu SD, dan sensor I2C 3.3V.",
    },
    {
        "part_no": "L298N",
        "category": "Dual Full-Bridge Motor Driver",
        "desc": "Driver jembatan-H ganda terintegrasi bertegangan tinggi (hingga 46V) dan arus puncak 2A per channel.",
        "common_uses": "Kendali arah putar dan kecepatan PWM 2 motor DC atau 1 motor stepper bipolar.",
    },
]


class RandomComponentView(discord.ui.View):
    """Tombol interaktif cepat untuk mengunduh datasheet atau melihat diagram pinout."""

    def __init__(self, part_no: str, timeout: float = 120.0):
        super().__init__(timeout=timeout)
        self.part_no = part_no

    @discord.ui.button(label="📄 Ambil Datasheet (Katalog)", style=discord.ButtonStyle.primary, emoji="📥")
    async def get_datasheet(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            f"💡 Ketik `/datasheet komponen:{self.part_no}` untuk menjelajah katalog lengkapnya!",
            ephemeral=True
        )

    @discord.ui.button(label="🔌 Lihat Pinout", style=discord.ButtonStyle.secondary, emoji="⚡")
    async def get_pinout(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            f"💡 Ketik `/pinout komponen:{self.part_no}` untuk melihat diagram kaki lengkapnya!",
            ephemeral=True
        )


class RandomCog(commands.Cog):
    """Cog slash command untuk rekomendasi dan undian komponen acak."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="random",
        description="Undi komponen elektronik acak untuk inspirasi proyek atau belajar praktikum"
    )
    async def random_cmd(self, interaction: discord.Interaction):
        item = random.choice(RANDOM_CURATED_COMPONENTS)

        embed = discord.Embed(
            title=f"🎲 Komponen Acak: {item['part_no']}",
            description=item["desc"],
            color=discord.Color.purple(),
        )
        embed.add_field(name="Kategori / Tipe", value=f"`{item['category']}`", inline=True)
        embed.add_field(name="Contoh Penggunaan", value=item["common_uses"], inline=False)
        embed.set_footer(text="Navigasi privat • Gunakan tombol di bawah untuk eksplorasi")

        view = RandomComponentView(item["part_no"])
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(RandomCog(bot))
