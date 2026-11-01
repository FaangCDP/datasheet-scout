"""
bots/discord/cogs/datasheet_cog.py -- Slash Command: /datasheet

Fitur:
1. Paginasi Katalog Interaktif (5 komponen per halaman) dengan tombol [◀ Sebelumnya] dan [Berikutnya ▶].
2. Navigasi 100% Ephemeral (hanya terlihat oleh pemanggil command, zero spam di server).
3. Pengiriman dokumen PDF & thumbnail langsung ke DM (Pesan Pribadi) pengguna.
4. Fallback otomatis ke ephemeral channel jika DM pengguna terkunci.
5. Pilihan kemasan interaktif (tombol variasi DIP, SOIC, dll).
6. Auto-clean gambar cover thumbnail lokal setelah dikirim ke Discord.
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

COMMON_COMPONENTS = [
    "ATmega328P", "ATmega2560", "ATmega32", "ATmega16", "ATtiny85", "ATtiny13",
    "Arduino Uno", "Arduino Nano", "Arduino Mega 2560", "Arduino Pro Mini",
    "ESP32", "ESP32-S3", "ESP32-CAM", "ESP8266", "NodeMCU",
    "STM32F103C8", "STM32F401CC", "RP2040", "Raspberry Pi Pico",
    "PIC16F877A", "PIC18F4550", "PIC16F883",
    "LM358", "LM324", "LM393", "LM339", "LM741", "TL072", "TL082", "NE5532", "OP07",
    "NE555", "LM555", "DS3231", "DS1307",
    "LM7805", "LM7809", "LM7812", "LM317", "AMS1117-3.3", "AMS1117-5.0",
    "LM2596", "XL6009", "TP4056",
    "BC547", "BC548", "BC557", "2N2222", "2N3904", "2N3906",
    "IRFZ44N", "IRF540N", "IRF3205", "TIP120", "TIP31C", "BD139", "BD140",
    "74HC595", "74HC165", "74HC00", "74HC04", "74HC08", "74HC32",
    "CD4017", "CD4051", "MAX232", "MAX485", "L293D", "L298N", "ULN2003",
    "TDA2003", "TDA2030", "TDA2050", "LM386", "PAM8403",
]

PACKAGE_CHOICES = [
    "DIP", "PDIP", "SOIC", "SOP", "TSSOP", "MSOP",
    "TO-92", "TO-220", "TO-126", "TO-3", "TO-247",
    "SOT-23", "SOT-223", "SOT-89",
    "TQFP", "LQFP", "QFP", "QFN", "PLCC", "BGA"
]


async def deliver_datasheet(
    interaction: discord.Interaction,
    res: dict,
    file_path: str,
    target_pkg: str | None = None
):
    """Fungsi pembantu mengirim datasheet ke DM atau fallback ephemeral."""
    part_no = res.get("part_no", "Component")
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

    specs = await asyncio.to_thread(extract_key_specs, file_path)
    for spec_key, spec_val in specs.items():
        embed.add_field(name=spec_key, value=spec_val, inline=True)

    if desc:
        embed.add_field(name="Deskripsi", value=desc[:1024], inline=False)
    embed.set_footer(text=f"Sumber: {source_site}.com")

    thumb_path = await asyncio.to_thread(extract_pdf_thumbnail, file_path)

    # Siapkan lampiran file
    if file_size_mb <= config.MAX_FILE_SIZE_MB:
        # Coba kirim via DM (Direct Message)
        try:
            files_dm = [discord.File(file_path, filename=os.path.basename(file_path))]
            if thumb_path and os.path.isfile(thumb_path):
                files_dm.append(discord.File(thumb_path, filename="thumb_preview.png"))
                embed.set_thumbnail(url="attachment://thumb_preview.png")

            await interaction.user.send(embed=embed, files=files_dm)
            await interaction.followup.send(
                f"📬 Datasheet **{part_no}** telah dikirim langsung ke **DM (Pesan Pribadi)** Anda!",
                ephemeral=True
            )
        except Exception:
            # Fallback jika DM terkunci: kirim di server secara ephemeral
            files_fallback = [discord.File(file_path, filename=os.path.basename(file_path))]
            if thumb_path and os.path.isfile(thumb_path):
                files_fallback.append(discord.File(thumb_path, filename="thumb_preview.png"))
                embed.set_thumbnail(url="attachment://thumb_preview.png")

            await interaction.followup.send(
                content="⚠️ *Pesan Pribadi (DM) Anda terkunci. Menampilkan dokumen secara privat di sini:*",
                embed=embed,
                files=files_fallback,
                ephemeral=True
            )
    else:
        embed.description = (
            f"⚠️ Ukuran file ({file_size_mb:.1f} MB) melebihi batas upload Discord "
            f"({config.MAX_FILE_SIZE_MB} MB).\nSilakan unduh langsung dari tautan judul di atas."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # Auto-clean thumbnail
    try:
        if thumb_path and os.path.isfile(thumb_path):
            os.remove(thumb_path)
    except OSError:
        pass


class CatalogSelectDropdown(discord.ui.Select):
    """Dropdown menu untuk memilih komponen mana dari 5 hasil di halaman aktif."""

    def __init__(self, page_items: list[dict], start_idx: int):
        options = []
        for i, item in enumerate(page_items, start=start_idx + 1):
            p_no = item.get("part_no", f"Item {i}")
            mfr = item.get("manufacturer", "Unknown")[:50]
            options.append(
                discord.SelectOption(
                    label=f"{i}. {p_no}"[:100],
                    description=f"Pabrikan: {mfr}"[:100],
                    value=str(i - 1),
                )
            )
        super().__init__(
            placeholder="Pilih komponen yang ingin diunduh PDF-nya...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        await self.view.handle_catalog_choice(interaction, int(self.values[0]))


class CatalogPaginationView(discord.ui.View):
    """View paginasi interaktif (5 hasil per halaman) dengan tombol Prev / Next."""

    PAGE_SIZE = 5

    def __init__(self, session, comp_name: str, all_results: list[dict], user_id: int, timeout: float = 120.0):
        super().__init__(timeout=timeout)
        self.session = session
        self.comp_name = comp_name
        self.all_results = all_results
        self.user_id = user_id
        self.current_page = 0
        self.total_pages = max(1, (len(all_results) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self.update_components()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Hanya pencari yang dapat mengontrol katalog ini.", ephemeral=True)
            return False
        return True

    def build_embed(self) -> discord.Embed:
        start = self.current_page * self.PAGE_SIZE
        end = min(start + self.PAGE_SIZE, len(self.all_results))
        page_items = self.all_results[start:end]

        embed = discord.Embed(
            title=f"📚 Katalog Datasheet: {self.comp_name}",
            description=(
                f"Ditemukan `{len(self.all_results)}` hasil pencarian.\n"
                f"Halaman **{self.current_page + 1} dari {self.total_pages}** (Menampilkan hasil {start + 1}–{end}):\n\n"
                f"*Pilih komponen dari menu dropdown di bawah untuk mengunduh PDF ke DM Anda.*"
            ),
            color=discord.Color.teal(),
        )

        for i, item in enumerate(page_items, start=start + 1):
            p_no = item.get("part_no", "-")
            mfr = item.get("manufacturer", "Unknown")
            desc = item.get("description", "-")[:120]
            src = item.get("source", "datasheet4u")
            embed.add_field(
                name=f"`{i}.` {p_no} ({mfr})",
                value=f"• Deskripsi: {desc}\n• Sumber: `{src}.com`",
                inline=False,
            )

        embed.set_footer(text="Navigasi privat • File PDF dikirim langsung ke DM")
        return embed

    def update_components(self):
        self.clear_items()
        start = self.current_page * self.PAGE_SIZE
        end = min(start + self.PAGE_SIZE, len(self.all_results))
        page_items = self.all_results[start:end]

        # 1. Dropdown pemilih item di halaman ini
        if page_items:
            self.add_item(CatalogSelectDropdown(page_items, start))

        # 2. Tombol Navigasi Prev
        btn_prev = discord.ui.Button(
            label="◀ Sebelumnya",
            style=discord.ButtonStyle.secondary,
            disabled=(self.current_page == 0),
            row=1
        )
        btn_prev.callback = self.prev_page
        self.add_item(btn_prev)

        # 3. Tombol Navigasi Next
        btn_next = discord.ui.Button(
            label="Berikutnya ▶",
            style=discord.ButtonStyle.primary,
            disabled=(self.current_page >= self.total_pages - 1),
            row=1
        )
        btn_next.callback = self.next_page
        self.add_item(btn_next)

    async def prev_page(self, interaction: discord.Interaction):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_components()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_components()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def handle_catalog_choice(self, interaction: discord.Interaction, index: int):
        if index < 0 or index >= len(self.all_results):
            await interaction.response.send_message("❌ Pilihan tidak valid.", ephemeral=True)
            return

        res = self.all_results[index]
        part_no = res.get("part_no", self.comp_name)
        mfr = res.get("manufacturer", "Unknown")
        source = res.get("source", "datasheet4u")

        await interaction.response.defer(ephemeral=True)

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
            await interaction.followup.send(f"❌ Gagal mengunduh file PDF untuk **{part_no}**.", ephemeral=True)
            return

        await deliver_datasheet(interaction, res, file_path)


class PackageSelectButton(discord.ui.Button):
    def __init__(self, label: str, custom_id: str, style=discord.ButtonStyle.primary):
        super().__init__(label=label, custom_id=custom_id, style=style)

    async def callback(self, interaction: discord.Interaction):
        await self.view.handle_package_choice(interaction, self.custom_id)


class PackageSelectionView(discord.ui.View):
    def __init__(self, session, comp_name: str, pkg_map: dict, timeout: float = 120.0):
        super().__init__(timeout=timeout)
        self.session = session
        self.comp_name = comp_name
        self.pkg_map = pkg_map

        for pkg_name, item in pkg_map.items():
            btn_label = f"📦 {pkg_name} ({item.get('part_no')})"[:80]
            self.add_item(PackageSelectButton(label=btn_label, custom_id=f"pkg_{pkg_name}"))

    async def handle_package_choice(self, interaction: discord.Interaction, custom_id: str):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        chosen = custom_id.replace("pkg_", "")
        res = self.pkg_map.get(chosen)
        if not res:
            await interaction.followup.send("❌ Varian kemasan tidak valid.", ephemeral=True)
            return

        part_no = res.get("part_no", self.comp_name)
        mfr = res.get("manufacturer", "Unknown")
        source_site = res.get("source", "datasheet4u")

        await interaction.response.defer(ephemeral=True)

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
            await interaction.followup.send(f"❌ Gagal mengunduh datasheet untuk `{chosen}`.", ephemeral=True)
            return

        await deliver_datasheet(interaction, res, file_path, target_pkg=chosen)


class DatasheetCog(commands.Cog):
    """Cog slash command pencarian dan pengunduhan datasheet."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = create_session()

    @app_commands.command(
        name="datasheet",
        description="Cari katalog datasheet PDF komponen elektronik (Paginasi 5 hasil & kirim ke DM)"
    )
    @app_commands.describe(
        komponen="Nama komponen elektronik yang dicari (Wajib, contoh: NE555, LM358, Arduino Uno)",
        kemasan="Bentuk kemasan fisik spesifik (Opsional, contoh: DIP, SOIC, TO-92, TO-220)",
        pilihan_kemasan="Tampilkan tombol pilihan kemasan fisik unik (Opsional, default: False)",
        jumlah="Jumlah total katalog yang dicari (Opsional, default: 15, maks: 25)",
        file="File .txt berisi daftar komponen tambahan (Opsional, 1 baris = 1 komponen)"
    )
    async def datasheet(
        self,
        interaction: discord.Interaction,
        komponen: str,
        kemasan: str | None = None,
        pilihan_kemasan: bool = False,
        jumlah: int = 15,
        file: discord.Attachment | None = None,
    ):
        comp_name = komponen.strip()
        if not comp_name:
            await interaction.response.send_message(
                "⚠️ Nama komponen wajib diisi dan tidak boleh kosong.",
                ephemeral=True,
            )
            return

        target_count = max(1, min(jumlah, 25))
        target_pkg = kemasan.strip().upper() if kemasan else None

        # Respons selalu ephemeral: hanya terlihat oleh pengguna yang mengetik
        await interaction.response.defer(thinking=True, ephemeral=True)

        # -----------------------------------------------------------------
        # KASUS 0: Pilihan Ragam Kemasan Unik
        # -----------------------------------------------------------------
        if pilihan_kemasan:
            base_query = clean_base_component(comp_name)
            raw_hits = await asyncio.to_thread(search_component, self.session, base_query, 25)

            if not raw_hits:
                await interaction.followup.send(
                    f"❌ Tidak ditemukan data untuk komponen **{comp_name}** (basis: `{base_query}`).",
                    ephemeral=True
                )
                return

            pkg_map = select_distinct_packages(raw_hits, max_items=5)
            if not pkg_map:
                await interaction.followup.send(
                    f"⚠️ Ditemukan hasil untuk **{comp_name}**, tetapi varian kemasan spesifik tidak terdeteksi otomatis.\n"
                    f"Silakan gunakan `/datasheet komponen:{comp_name}` untuk melihat katalog lengkap.",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title=f"📦 Pilihan Kemasan Fisik: {base_query}",
                description="Pilih salah satu tombol kemasan di bawah ini untuk mengunduh PDF ke DM Anda:",
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

            view = PackageSelectionView(self.session, base_query, pkg_map)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            return

        # -----------------------------------------------------------------
        # KASUS A: Batch Search via File Attachment .txt
        # -----------------------------------------------------------------
        if file is not None:
            if not file.filename.lower().endswith(".txt"):
                await interaction.followup.send("⚠️ Format file lampiran harus berupa file teks berakhiran `.txt`.", ephemeral=True)
                return

            try:
                raw_bytes = await file.read()
                try:
                    text_content = raw_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    text_content = raw_bytes.decode("latin-1", errors="ignore")
            except Exception as e:
                await interaction.followup.send(f"❌ Gagal membaca file lampiran: {e}", ephemeral=True)
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
            await interaction.followup.send(
                f"⏳ Sedang memproses **{len(process_list)} komponen** (file ZIP akan dikirimkan ke DM Anda)...",
                ephemeral=True
            )

            downloaded = []
            for comp in process_list:
                results = await asyncio.to_thread(search_component, self.session, comp, 1)
                if not results:
                    continue
                res = results[0]
                part_no = res.get("part_no", comp)
                mfr = res.get("manufacturer", "Unknown")
                source = res.get("source", "datasheet4u")
                fn = sanitize_filename(part_no, mfr, source=source)
                exp = os.path.join(config.DOWNLOAD_DIR, fn)
                if os.path.isfile(exp) and os.path.getsize(exp) > 1000:
                    downloaded.append((res, exp))
                else:
                    fp = await asyncio.to_thread(download_single, self.session, res, 1, config.DOWNLOAD_DIR)
                    if fp and os.path.isfile(fp):
                        downloaded.append((res, fp))

            if not downloaded:
                await interaction.followup.send("❌ Tidak ada datasheet yang berhasil diunduh.", ephemeral=True)
                return

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for res, path in downloaded:
                    zf.write(path, arcname=os.path.basename(path))

            zip_buffer.seek(0)
            zip_file = discord.File(zip_buffer, filename=f"{comp_name}_batch_datasheets.zip")
            try:
                await interaction.user.send(content=f"📦 Berikut arsip ZIP untuk {len(downloaded)} komponen:", file=zip_file)
                await interaction.followup.send("📬 File ZIP berhasil dikirim ke **DM (Pesan Pribadi)** Anda!", ephemeral=True)
            except Exception:
                await interaction.followup.send(content="⚠️ DM terkunci. File dikirim di sini:", file=zip_file, ephemeral=True)
            return

        # -----------------------------------------------------------------
        # KASUS B: Pencarian Reguler (Paginasi 5 Hasil per Halaman)
        # -----------------------------------------------------------------
        results = await asyncio.to_thread(search_component, self.session, comp_name, target_count)
        if not results:
            await interaction.followup.send(
                f"❌ Tidak ditemukan datasheet untuk komponen **{comp_name}** di database.",
                ephemeral=True
            )
            return

        # Sortir kemasan jika ditentukan pengguna
        if target_pkg:
            def pkg_match_score(r):
                txt = f"{r.get('part_no', '')} {r.get('description', '')}".upper()
                return 2 if target_pkg in txt else 0
            results.sort(key=pkg_match_score, reverse=True)

        # Buat View Paginasi (5 hasil per halaman)
        view = CatalogPaginationView(self.session, comp_name, results, interaction.user.id)
        embed = view.build_embed()
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @datasheet.autocomplete('komponen')
    async def komponen_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        catalog = set(COMMON_COMPONENTS)

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
