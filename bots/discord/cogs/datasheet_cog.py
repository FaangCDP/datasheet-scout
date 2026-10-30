"""
bots/discord/cogs/datasheet_cog.py -- Slash Command: /datasheet
Parameter:
- komponen: str (Wajib)
- jumlah: int (Opsional, default = 1)
- file: discord.Attachment (Opsional)
"""

import asyncio
import io
import os
import zipfile
import discord
from discord import app_commands
from discord.ext import commands

from core.scraper import (
    create_session,
    search_component,
    download_single,
    sanitize_filename,
)
from core.preview_extractor import extract_pdf_thumbnail
from core.specs_extractor import extract_key_specs
from core.package_classifier import (
    clean_base_component,
    select_distinct_packages,
)
from bots.discord import config

# Katalog komponen praktikum umum untuk saran instan autocomplete
COMMON_COMPONENTS = [
    # Mikrokontroler & Development Board
    "ATmega328P", "ATmega2560", "ATmega32", "ATmega16", "ATtiny85", "ATtiny13",
    "Arduino Uno", "Arduino Nano", "Arduino Mega 2560", "Arduino Pro Mini",
    "ESP32", "ESP32-S3", "ESP32-CAM", "ESP8266", "NodeMCU",
    "STM32F103C8", "STM32F401CC", "RP2040", "Raspberry Pi Pico",
    "PIC16F877A", "PIC18F4550", "PIC16F883",
    # Op-Amp, Komparator & Linear IC
    "LM358", "LM324", "LM393", "LM339", "LM741", "TL072", "TL082", "NE5532", "OP07",
    # Timer & RTC
    "NE555", "LM555", "DS3231", "DS1307",
    # Regulator Tegangan & Power
    "LM7805", "LM7809", "LM7812", "LM317", "AMS1117-3.3", "AMS1117-5.0",
    "LM2596", "XL6009", "TP4056",
    # Transistor BJT & MOSFET
    "BC547", "BC548", "BC557", "2N2222", "2N3904", "2N3906",
    "IRFZ44N", "IRF540N", "IRF3205", "TIP120", "TIP31C", "BD139", "BD140",
    # IC Logika Digital & Driver
    "74HC595", "74HC165", "74HC00", "74HC04", "74HC08", "74HC32",
    "CD4017", "CD4051", "MAX232", "MAX485", "L293D", "L298N", "ULN2003",
    # Audio Amplifier IC
    "TDA2003", "TDA2030", "TDA2050", "LM386", "PAM8403",
]


# Kemasan / Package fisik komponen yang umum digunakan
PACKAGE_CHOICES = [
    "DIP", "PDIP", "SOIC", "SOP", "TSSOP", "MSOP",
    "TO-92", "TO-220", "TO-126", "TO-3", "TO-247",
    "SOT-23", "SOT-223", "SOT-89",
    "TQFP", "LQFP", "QFP", "QFN", "PLCC", "BGA"
]


class PackageSelectButton(discord.ui.Button):
    """Tombol pilihan kemasan individual."""

    def __init__(self, label: str, custom_id: str, style=discord.ButtonStyle.primary):
        super().__init__(label=label, custom_id=custom_id, style=style)

    async def callback(self, interaction: discord.Interaction):
        # Callback didelegasikan ke view induk
        await self.view.handle_package_choice(interaction, self.custom_id)


class PackageSelectionView(discord.ui.View):
    """View tombol interaktif untuk memilih kemasan mana yang ingin diunduh."""

    def __init__(self, session, comp_name: str, pkg_map: dict, timeout: float = 120.0):
        super().__init__(timeout=timeout)
        self.session = session
        self.comp_name = comp_name
        self.pkg_map = pkg_map  # {"DIP": item_dict, "SOIC": item_dict, ...}

        # Tambahkan 1 tombol per kemasan unik
        for pkg_name, item in pkg_map.items():
            btn_label = f"📦 {pkg_name} ({item.get('part_no')})"[:80]
            self.add_item(PackageSelectButton(label=btn_label, custom_id=f"pkg_{pkg_name}"))

        # Tombol download semua sekaligus
        if len(pkg_map) > 1:
            self.add_item(
                PackageSelectButton(
                    label="📦 Unduh Semua (ZIP)",
                    custom_id="pkg_ALL",
                    style=discord.ButtonStyle.success,
                )
            )

    async def handle_package_choice(self, interaction: discord.Interaction, custom_id: str):
        # Nonaktifkan tombol setelah diklik agar tidak terjadi double-request
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        chosen = custom_id.replace("pkg_", "")
        followup_msg = await interaction.followup.send(f"⏳ Sedang mengunduh varian `{chosen}`...", ephemeral=True)

        # -------------------------------------------------------------
        # Pilihan: Unduh Semua Package (ZIP)
        # -------------------------------------------------------------
        if chosen == "ALL":
            downloaded = []
            for pkg, res in self.pkg_map.items():
                part_no = res.get("part_no", self.comp_name)
                mfr = res.get("manufacturer", "Unknown")
                source = res.get("source", "datasheet4u")
                expected_fn = sanitize_filename(part_no, mfr, source=source)
                expected_path = os.path.join(config.DOWNLOAD_DIR, expected_fn)

                is_cached = (
                    os.path.isfile(expected_path)
                    and os.path.getsize(expected_path) > 1000
                    and os.path.getsize(expected_path) != 25307
                )
                if is_cached:
                    downloaded.append((res, expected_path))
                else:
                    file_path = await asyncio.to_thread(
                        download_single, self.session, res, 1, config.DOWNLOAD_DIR
                    )
                    if file_path and os.path.isfile(file_path) and os.path.getsize(file_path) != 25307:
                        downloaded.append((res, file_path))

            if not downloaded:
                await followup_msg.edit(content="❌ Gagal mengunduh file PDF untuk seluruh varian.")
                return

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for res, path in downloaded:
                    zip_file.write(path, arcname=os.path.basename(path))

            zip_buffer.seek(0)
            zip_size_mb = len(zip_buffer.getvalue()) / (1024 * 1024)

            embed = discord.Embed(
                title=f"📦 Semua Kemasan: {self.comp_name} ({len(downloaded)} file)",
                description=f"Berhasil mengunduh `{len(downloaded)}` varian kemasan unik.",
                color=discord.Color.green(),
            )
            for res, path in downloaded:
                embed.add_field(name=res.get("part_no"), value=f"• Pabrikan: {res.get('manufacturer')}", inline=False)

            if zip_size_mb <= config.MAX_FILE_SIZE_MB:
                discord_attachment = discord.File(
                    zip_buffer, filename=f"{self.comp_name}_all_packages.zip"
                )
                await followup_msg.edit(content=None, embed=embed)
                await interaction.followup.send(file=discord_attachment, ephemeral=True)
            else:
                await followup_msg.edit(content="⚠️ Ukuran zip melebihi limit upload Discord.")
            return

        # -------------------------------------------------------------
        # Pilihan: Unduh 1 Package Tertentu
        # -------------------------------------------------------------
        res = self.pkg_map.get(chosen)
        if not res:
            await followup_msg.edit(content="❌ Varian kemasan tidak valid.")
            return

        part_no = res.get("part_no", self.comp_name)
        mfr = res.get("manufacturer", "Unknown")
        desc = res.get("description", "Tidak ada deskripsi.")
        detail_url = res.get("url", "")
        source_site = res.get("source", "datasheet4u")

        expected_fn = sanitize_filename(part_no, mfr, source=source_site)
        expected_path = os.path.join(config.DOWNLOAD_DIR, expected_fn)

        is_cached = (
            os.path.isfile(expected_path)
            and os.path.getsize(expected_path) > 1000
            and os.path.getsize(expected_path) != 25307
        )
        if is_cached:
            file_path = expected_path
        else:
            file_path = await asyncio.to_thread(
                download_single, self.session, res, 1, config.DOWNLOAD_DIR
            )

        if not file_path or not os.path.isfile(file_path):
            await followup_msg.edit(content=f"❌ Gagal mengunduh datasheet untuk kemasan `{chosen}`.")
            return

        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        embed = discord.Embed(
            title=f"📄 Datasheet: {part_no} ({chosen})",
            url=detail_url,
            color=discord.Color.blue(),
        )
        embed.add_field(name="Pabrikan", value=mfr, inline=True)
        embed.add_field(name="Kemasan", value=f"`{chosen}`", inline=True)
        embed.add_field(name="Ukuran File", value=f"{file_size_mb:.2f} MB", inline=True)

        specs = await asyncio.to_thread(extract_key_specs, file_path)
        for spec_key, spec_val in specs.items():
            embed.add_field(name=spec_key, value=spec_val, inline=True)

        if desc:
            embed.add_field(name="Deskripsi", value=desc[:1024], inline=False)
        embed.set_footer(text=f"Sumber: {source_site}.com")

        discord_file = discord.File(file_path, filename=os.path.basename(file_path))
        files_to_send = [discord_file]

        thumb_path = await asyncio.to_thread(extract_pdf_thumbnail, file_path)
        if thumb_path and os.path.isfile(thumb_path):
            thumb_file = discord.File(thumb_path, filename="thumb_preview.png")
            embed.set_thumbnail(url="attachment://thumb_preview.png")
            files_to_send.append(thumb_file)

        await followup_msg.edit(content=None, embed=embed)
        await interaction.followup.send(files=files_to_send, ephemeral=True)


class DatasheetCog(commands.Cog):
    """Cog slash command pencarian dan pengunduhan datasheet."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = create_session()

    @app_commands.command(
        name="datasheet",
        description="Cari dan unduh datasheet PDF komponen elektronik"
    )
    @app_commands.describe(
        komponen="Nama komponen elektronik yang dicari (Wajib, contoh: NE555, LM358, Arduino Uno)",
        kemasan="Bentuk kemasan fisik spesifik (Opsional, contoh: DIP, SOIC, TO-92, TO-220)",
        pilihan_kemasan="Tampilkan tombol interaktif untuk memilih kemasan sebelum mengunduh (Opsional, default: False)",
        jumlah="Jumlah varian datasheet yang ingin dicari/diunduh (Opsional, default: 1)",
        file="File .txt berisi daftar komponen tambahan (Opsional, 1 baris = 1 komponen)"
    )
    async def datasheet(
        self,
        interaction: discord.Interaction,
        komponen: str,
        kemasan: str | None = None,
        pilihan_kemasan: bool = False,
        jumlah: int = 1,
        file: discord.Attachment | None = None,
    ):
        comp_name = komponen.strip()
        if not comp_name:
            await interaction.response.send_message(
                "⚠️ Nama komponen wajib diisi dan tidak boleh kosong.",
                ephemeral=True,
            )
            return

        target_count = max(1, min(jumlah, 10))
        target_pkg = kemasan.strip().upper() if kemasan else None
        await interaction.response.defer(thinking=True)

        # =====================================================================
        # KASUS 0: Fitur Pilihan Kemasan Interaktif (Tombol Pilihan Package)
        # =====================================================================
        if pilihan_kemasan:
            # Pangkas suffix bias kemasan pada query agar pencarian katalog bersih
            base_query = clean_base_component(comp_name)
            raw_hits = await asyncio.to_thread(search_component, self.session, base_query, 25)

            if not raw_hits:
                await interaction.followup.send(
                    f"❌ Tidak ditemukan data untuk komponen **{comp_name}** (basis: `{base_query}`)."
                )
                return

            pkg_map = select_distinct_packages(raw_hits, max_items=5)
            if not pkg_map:
                await interaction.followup.send(
                    f"⚠️ Ditemukan hasil untuk **{comp_name}**, tetapi varian kemasan spesifik tidak terdeteksi secara otomatis.\n"
                    f"Silakan gunakan `/datasheet komponen:{comp_name}` untuk mengunduh versi standar."
                )
                return

            embed = discord.Embed(
                title=f"📦 Pilihan Kemasan Fisik: {base_query}",
                description=(
                    f"Ditemukan `{len(pkg_map)}` varian kemasan fisik unik untuk **{base_query}**.\n"
                    f"Silakan **klik tombol kemasan** di bawah ini untuk mengunduh PDF yang sesuai:"
                ),
                color=discord.Color.gold(),
            )
            for pkg_name, item in pkg_map.items():
                p_no = item.get("part_no", base_query)
                m_fr = item.get("manufacturer", "Unknown")
                embed.add_field(
                    name=f"Kemasan: {pkg_name}",
                    value=f"• Part: `{p_no}`\n• Pabrikan: {m_fr}",
                    inline=True,
                )

            embed.set_footer(text="Pilih tombol untuk hemat kuota dan ruang disk • Timeout 2 menit")
            view = PackageSelectionView(self.session, base_query, pkg_map)
            await interaction.followup.send(embed=embed, view=view)
            return

        # =====================================================================
        # KASUS A: Pengguna melampirkan file .txt (Batch Search)
        # =====================================================================
        if file is not None:
            if not file.filename.lower().endswith(".txt"):
                await interaction.followup.send("⚠️ Format file lampiran harus berupa file teks berakhiran `.txt`.")
                return

            try:
                raw_bytes = await file.read()
                try:
                    text_content = raw_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    text_content = raw_bytes.decode("latin-1", errors="ignore")
            except Exception as e:
                await interaction.followup.send(f"❌ Gagal membaca file lampiran: {e}")
                return

            components = [comp_name]
            seen = {comp_name.upper()}
            for line in text_content.splitlines():
                name = line.strip()
                if not name or name.startswith("#"):
                    continue
                if name.upper() not in seen:
                    seen.add(name.upper())
                    components.append(name)

            MAX_BATCH = 10
            process_list = components[:MAX_BATCH]
            extra_msg = f" (dibatasi {MAX_BATCH} komponen)" if len(components) > MAX_BATCH else ""

            status_msg = await interaction.followup.send(
                f"⏳ Sedang memproses **{len(process_list)} komponen**{extra_msg} (maks `{target_count}` varian per komponen)..."
            )

            downloaded_files = []
            not_found = []

            for comp in process_list:
                results = await asyncio.to_thread(search_component, self.session, comp, target_count)
                if not results:
                    not_found.append(comp)
                    continue

                for res in results:
                    part_no = res.get("part_no", comp)
                    mfr = res.get("manufacturer", "Unknown")
                    source = res.get("source", "datasheet4u")
                    expected_fn = sanitize_filename(part_no, mfr, source=source)
                    expected_path = os.path.join(config.DOWNLOAD_DIR, expected_fn)

                    is_cached = (
                        os.path.isfile(expected_path)
                        and os.path.getsize(expected_path) > 1000
                        and os.path.getsize(expected_path) != 25307
                    )
                    if is_cached:
                        downloaded_files.append((part_no, expected_path))
                    else:
                        saved_path = await asyncio.to_thread(
                            download_single, self.session, res, 1, config.DOWNLOAD_DIR
                        )
                        if saved_path and os.path.isfile(saved_path) and os.path.getsize(saved_path) != 25307:
                            downloaded_files.append((part_no, saved_path))
                        else:
                            not_found.append(comp)

            if not downloaded_files:
                await status_msg.edit(
                    content="❌ Tidak ada datasheet yang berhasil ditemukan/diunduh untuk daftar komponen tersebut."
                )
                return

            total_bytes = sum(os.path.getsize(path) for _, path in downloaded_files)
            total_mb = total_bytes / (1024 * 1024)

            summary_desc = (
                f"✅ **{len(downloaded_files)} file** berhasil diunduh dari {len(process_list)} komponen.\n"
                f"📦 Total ukuran: `{total_mb:.2f} MB`\n"
            )
            if not_found:
                summary_desc += f"⚠️ Tidak ditemukan / gagal: {', '.join(set(not_found))}\n"

            embed = discord.Embed(
                title="📦 Hasil Batch Datasheet (.txt)",
                description=summary_desc,
                color=discord.Color.green(),
            )
            embed.set_footer(text="Sumber: Multi-Database (datasheet4u.com & alldatasheet.com)")

            if len(downloaded_files) > 1:
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    for part, path in downloaded_files:
                        zip_file.write(path, arcname=os.path.basename(path))

                zip_buffer.seek(0)
                zip_size_mb = len(zip_buffer.getvalue()) / (1024 * 1024)

                if zip_size_mb <= config.MAX_FILE_SIZE_MB:
                    discord_attachment = discord.File(
                        zip_buffer, filename=f"datasheets_batch_{len(downloaded_files)}_files.zip"
                    )
                    await status_msg.edit(content=None, embed=embed)
                    await interaction.followup.send(file=discord_attachment)
                else:
                    embed.description += (
                        f"\n⚠️ Ukuran arsip zip ({zip_size_mb:.1f} MB) melebihi batas upload Discord "
                        f"({config.MAX_FILE_SIZE_MB} MB)."
                    )
                    await status_msg.edit(content=None, embed=embed)
            else:
                single_part, single_path = downloaded_files[0]
                single_mb = os.path.getsize(single_path) / (1024 * 1024)
                if single_mb <= config.MAX_FILE_SIZE_MB:
                    discord_attachment = discord.File(single_path, filename=os.path.basename(single_path))
                    await status_msg.edit(content=None, embed=embed)
                    await interaction.followup.send(file=discord_attachment)
                else:
                    await status_msg.edit(content=None, embed=embed)
            return

        # =====================================================================
        # KASUS B: Pencarian komponen tunggal (dengan target_count)
        # =====================================================================
        # Jika kemasan ditentukan, ambil lebih banyak kandidat untuk difilter berdasarkan kemasan
        fetch_limit = target_count * 3 if target_pkg else target_count
        results = await asyncio.to_thread(search_component, self.session, comp_name, fetch_limit)

        if not results:
            await interaction.followup.send(
                f"❌ Tidak ditemukan datasheet untuk komponen **{comp_name}** di database."
            )
            return

        # Filter / Sortir hasil jika kemasan ditentukan
        if target_pkg:
            def pkg_match_score(r):
                text_to_check = f"{r.get('part_no', '')} {r.get('description', '')}".upper()
                if target_pkg in text_to_check:
                    return 2
                # Cek variasi DIP vs PDIP
                if target_pkg in ("DIP", "PDIP") and any(d in text_to_check for d in ("DIP", "PDIP")):
                    return 2
                if target_pkg in ("SOIC", "SOP") and any(s in text_to_check for s in ("SOIC", "SOP")):
                    return 2
                return 0

            results.sort(key=pkg_match_score, reverse=True)
            results = results[:target_count]

        downloaded = []
        for res in results:
            part_no = res.get("part_no", comp_name)
            mfr = res.get("manufacturer", "Unknown")
            source = res.get("source", "datasheet4u")
            filename = sanitize_filename(part_no, mfr, source=source)
            expected_file = os.path.join(config.DOWNLOAD_DIR, filename)

            is_cached = (
                os.path.isfile(expected_file)
                and os.path.getsize(expected_file) > 1000
                and os.path.getsize(expected_file) != 25307
            )
            if is_cached:
                downloaded.append((res, expected_file))
            else:
                file_path = await asyncio.to_thread(
                    download_single, self.session, res, 1, config.DOWNLOAD_DIR
                )
                if file_path and os.path.isfile(file_path) and os.path.getsize(file_path) != 25307:
                    downloaded.append((res, file_path))

        if not downloaded:
            await interaction.followup.send(
                f"⚠️ Berhasil menemukan varian untuk **{comp_name}**, tetapi gagal mengunduh PDF."
            )
            return

        # Jika hanya 1 file (default)
        if len(downloaded) == 1:
            res, file_path = downloaded[0]
            part_no = res.get("part_no", comp_name)
            mfr = res.get("manufacturer", "Unknown")
            desc = res.get("description", "Tidak ada deskripsi.")
            detail_url = res.get("url", "")
            source_site = res.get("source", "datasheet4u")
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)

            embed = discord.Embed(
                title=f"📄 Datasheet: {part_no}",
                url=detail_url,
                color=discord.Color.blue(),
            )
            embed.add_field(name="Pabrikan", value=mfr, inline=True)
            embed.add_field(name="Ukuran File", value=f"{file_size_mb:.2f} MB", inline=True)

            if target_pkg:
                embed.add_field(name="Kemasan Diminta", value=f"`{target_pkg}`", inline=True)

            # Ekstrak ringkasan spesifikasi kunci (Tegangan, Clock, Package, dll.)
            specs = await asyncio.to_thread(extract_key_specs, file_path)
            for spec_key, spec_val in specs.items():
                embed.add_field(name=spec_key, value=spec_val, inline=True)

            if desc:
                embed.add_field(name="Deskripsi", value=desc[:1024], inline=False)
            embed.set_footer(text=f"Sumber: {source_site}.com")

            if file_size_mb <= config.MAX_FILE_SIZE_MB:
                discord_file = discord.File(file_path, filename=os.path.basename(file_path))
                files_to_send = [discord_file]

                thumb_path = await asyncio.to_thread(extract_pdf_thumbnail, file_path)
                if thumb_path and os.path.isfile(thumb_path):
                    thumb_file = discord.File(thumb_path, filename="thumb_preview.png")
                    embed.set_thumbnail(url="attachment://thumb_preview.png")
                    files_to_send.append(thumb_file)

                await interaction.followup.send(embed=embed, files=files_to_send)
            else:
                embed.description = (
                    f"⚠️ Ukuran file ({file_size_mb:.1f} MB) melebihi batas upload Discord "
                    f"({config.MAX_FILE_SIZE_MB} MB).\nSilakan unduh langsung dari link di atas."
                )
                await interaction.followup.send(embed=embed)

        else:
            # Jika user meminta lebih dari 1 varian (> 1 file)
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for res, path in downloaded:
                    zip_file.write(path, arcname=os.path.basename(path))

            zip_buffer.seek(0)
            zip_size_mb = len(zip_buffer.getvalue()) / (1024 * 1024)

            embed = discord.Embed(
                title=f"📦 Datasheet Varian: {comp_name} ({len(downloaded)} file)",
                description=f"Berhasil mengunduh `{len(downloaded)}` varian datasheet untuk **{comp_name}**.",
                color=discord.Color.blue(),
            )
            for res, path in downloaded:
                p_no = res.get("part_no", comp_name)
                m_fr = res.get("manufacturer", "Unknown")
                embed.add_field(name=p_no, value=f"• Pabrikan: {m_fr}", inline=False)

            embed.set_footer(text="Multi-Database Search")

            if zip_size_mb <= config.MAX_FILE_SIZE_MB:
                discord_attachment = discord.File(
                    zip_buffer, filename=f"{comp_name}_datasheets_{len(downloaded)}_variants.zip"
                )
                await interaction.followup.send(embed=embed, file=discord_attachment)
            else:
                embed.description += f"\n⚠️ Ukuran arsip ({zip_size_mb:.1f} MB) melebihi batas upload Discord."
                await interaction.followup.send(embed=embed)

    @datasheet.autocomplete('komponen')
    async def komponen_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Menyajikan saran instan (autocomplete) nama komponen secara real-time."""
        catalog = set(COMMON_COMPONENTS)

        # Sertakan komponen dari file folder list/
        import glob
        list_dir = os.path.join(os.path.dirname(config.DOWNLOAD_DIR), "list")
        for f in glob.glob(os.path.join(list_dir, "*.txt")):
            try:
                with open(f, encoding="utf-8", errors="ignore") as fp:
                    for line in fp:
                        c = line.strip()
                        if c and not c.startswith("#"):
                            catalog.add(c)
            except OSError:
                pass

        # Sertakan komponen yang sudah ada di folder downloads/
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

    @datasheet.autocomplete('kemasan')
    async def kemasan_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Menyajikan saran pilihan kemasan (package) fisik komponen."""
        cur = current.strip().upper()
        if not cur:
            suggestions = PACKAGE_CHOICES[:25]
        else:
            starts = [p for p in PACKAGE_CHOICES if p.startswith(cur)]
            contains = [p for p in PACKAGE_CHOICES if cur in p and p not in starts]
            suggestions = (starts + contains)[:25]

        return [app_commands.Choice(name=p, value=p) for p in suggestions]


async def setup(bot: commands.Bot):
    await bot.add_cog(DatasheetCog(bot))
