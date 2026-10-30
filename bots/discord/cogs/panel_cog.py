"""
bots/discord/cogs/panel_cog.py -- Slash Command: /panel (Owner Only Dashboard)

Menyajikan dashboard interaktif khusus owner dengan:
1. Auto-refresh otomatis setiap 5 detik (live update tanpa perlu klik refresh manual).
2. Status latensi bot Discord secara real-time.
3. Health check status koneksi database sumber (datasheet4u.com & alldatasheet.com).
4. Pemantauan resource VPS (CPU load, RAM, Disk storage).
5. Navigasi isi disk & penghapusan file cache PDF tertentu.
6. Pembersihan cache gambar (thumbnails & pinouts).
7. Sinkronisasi command tree langsung dari Discord.
"""

import asyncio
import os
import shutil
import time
import discord
from discord import app_commands
from discord.ext import commands

import requests as std_requests
from curl_cffi import requests as cffi_requests
from bots.discord import config


def get_vps_stats() -> dict:
    """Membaca statistik resource sistem VPS/Host."""
    total, used, free = shutil.disk_usage("/")
    disk_total_gb = total / (1024**3)
    disk_used_gb = used / (1024**3)
    disk_free_gb = free / (1024**3)
    disk_percent = round((used / total) * 100, 1)

    ram_total_gb = 0.0
    ram_used_gb = 0.0
    ram_avail_gb = 0.0
    ram_percent = 0.0

    if os.path.exists("/proc/meminfo"):
        try:
            mem = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        mem[parts[0].strip()] = int(parts[1].split()[0])
            t = mem.get("MemTotal", 0) / 1024 / 1024
            a = mem.get("MemAvailable", 0) / 1024 / 1024
            u = t - a
            ram_total_gb = round(t, 2)
            ram_used_gb = round(u, 2)
            ram_avail_gb = round(a, 2)
            ram_percent = round((u / t) * 100, 1) if t > 0 else 0.0
        except Exception:
            pass

    load1, load5, load15 = (0.0, 0.0, 0.0)
    try:
        load1, load5, load15 = os.getloadavg()
    except Exception:
        pass

    return {
        "disk_total": disk_total_gb,
        "disk_used": disk_used_gb,
        "disk_free": disk_free_gb,
        "disk_percent": disk_percent,
        "ram_total": ram_total_gb,
        "ram_used": ram_used_gb,
        "ram_avail": ram_avail_gb,
        "ram_percent": ram_percent,
        "load": f"{load1:.2f}, {load5:.2f}, {load15:.2f}",
    }


def get_cache_summary() -> dict:
    """Menghitung ringkasan isi folder downloads."""
    summary = {
        "pdf_files": [],
        "thumb_files": [],
        "pinout_files": [],
        "pdf_size": 0,
        "thumb_size": 0,
        "pinout_size": 0,
    }

    if not os.path.isdir(config.DOWNLOAD_DIR):
        return summary

    for root, _, files in os.walk(config.DOWNLOAD_DIR):
        for f in files:
            full_p = os.path.join(root, f)
            try:
                sz = os.path.getsize(full_p)
            except OSError:
                sz = 0

            if ".thumbnails" in root:
                summary["thumb_files"].append((f, full_p, sz))
                summary["thumb_size"] += sz
            elif ".pinouts" in root:
                summary["pinout_files"].append((f, full_p, sz))
                summary["pinout_size"] += sz
            elif f.lower().endswith(".pdf"):
                summary["pdf_files"].append((f, full_p, sz))
                summary["pdf_size"] += sz

    return summary


def check_sources_health() -> dict:
    """Cek status konektivitas dan latensi ke database sumber."""
    results = {}

    # 1. Cek datasheet4u.com
    t0 = time.time()
    try:
        r1 = std_requests.get("https://datasheet4u.com/", timeout=4, headers={"User-Agent": "Mozilla/5.0"})
        ms1 = round((time.time() - t0) * 1000)
        status1 = "🟢 Aktif" if r1.status_code == 200 else f"🟡 HTTP {r1.status_code}"
    except Exception:
        ms1 = round((time.time() - t0) * 1000)
        status1 = "🔴 Gangguan"
    results["datasheet4u"] = (status1, ms1)

    # 2. Cek alldatasheet.com
    t0 = time.time()
    try:
        r2 = cffi_requests.get("https://www.alldatasheet.com/", timeout=4, impersonate="chrome124")
        ms2 = round((time.time() - t0) * 1000)
        status2 = "🟢 Aktif" if r2.status_code == 200 else f"🟡 HTTP {r2.status_code}"
    except Exception:
        ms2 = round((time.time() - t0) * 1000)
        status2 = "🔴 Gangguan"
    results["alldatasheet"] = (status2, ms2)

    return results


class DeleteFileSelect(discord.ui.Select):
    """Dropdown menu untuk memilih file PDF spesifik yang ingin dihapus."""

    def __init__(self, pdf_list: list[tuple]):
        options = []
        for fname, fpath, sz in pdf_list[:25]:
            sz_str = f"{sz / 1024:.1f} KB" if sz < 1024 * 1024 else f"{sz / 1024 / 1024:.2f} MB"
            options.append(
                discord.SelectOption(
                    label=fname[:100],
                    description=f"Ukuran: {sz_str}",
                    value=fname,
                )
            )
        super().__init__(
            placeholder="Pilih file PDF tertentu yang ingin dihapus...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        selected_name = self.values[0]
        deleted_count = 0
        deleted_bytes = 0

        for root, _, files in os.walk(config.DOWNLOAD_DIR):
            if selected_name in files:
                target = os.path.join(root, selected_name)
                try:
                    deleted_bytes += os.path.getsize(target)
                    os.remove(target)
                    deleted_count += 1
                except Exception as e:
                    await interaction.response.send_message(f"❌ Gagal menghapus {selected_name}: {e}", ephemeral=True)
                    return

        sz_mb = deleted_bytes / (1024 * 1024)
        await interaction.response.send_message(
            f"🗑️ Berhasil menghapus file `{selected_name}` (`{sz_mb:.2f} MB`).",
            ephemeral=True,
        )


class OwnerPanelView(discord.ui.View):
    """View tombol kontrol untuk panel owner dengan auto-refresh otomatis."""

    def __init__(self, bot: commands.Bot, owner_id: int, timeout: float = 900.0):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.owner_id = owner_id
        self.message = None
        self.is_active = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.owner_id and interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "❌ Akses ditolak. Panel ini hanya dapat dikontrol oleh Owner bot.",
                ephemeral=True,
            )
            return False
        return True

    async def start_auto_refresh(self, message: discord.InteractionMessage):
        """Loop auto-refresh otomatis setiap 1 menit (60 detik) tanpa membebani WAF server."""
        self.message = message
        while self.is_active:
            await asyncio.sleep(60)
            if not self.is_active:
                break
            try:
                embed = await asyncio.to_thread(self.build_panel_embed)
                await self.message.edit(embed=embed, view=self)
            except discord.NotFound:
                break
            except Exception:
                pass

    def stop_refresh(self):
        self.is_active = False

    async def on_timeout(self):
        self.stop_refresh()
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

    def build_panel_embed(self) -> discord.Embed:
        stats = get_vps_stats()
        cache = get_cache_summary()
        sources = check_sources_health()
        
        # Tangani kemungkinan latency bernilai float NaN saat bot baru start/offline test
        raw_lat = self.bot.latency
        bot_latency = round(raw_lat * 1000) if raw_lat is not None and not (raw_lat != raw_lat) else 0

        total_cache_bytes = cache["pdf_size"] + cache["thumb_size"] + cache["pinout_size"]
        total_cache_mb = total_cache_bytes / (1024 * 1024)

        embed = discord.Embed(
            title="⚙️ Panel Kontrol & Resource Server (Owner Only)",
            color=discord.Color.dark_purple(),
        )

        # Bagian 1: Latensi Bot & Status Koneksi Sumber
        d4u_stat, d4u_ms = sources.get("datasheet4u", ("-", 0))
        all_stat, all_ms = sources.get("alldatasheet", ("-", 0))

        embed.add_field(
            name="⚡ Status Jaringan & Latensi",
            value=(
                f"• **Gateway Discord**: `{bot_latency} ms`\n"
                f"• **datasheet4u.com**: {d4u_stat} (`{d4u_ms} ms`)\n"
                f"• **alldatasheet.com**: {all_stat} (`{all_ms} ms`)"
            ),
            inline=False,
        )

        # Bagian 2: Resource VPS
        embed.add_field(
            name="💻 Resource VPS / Host",
            value=(
                f"• **Disk (/)**: `{stats['disk_used']:.1f}/{stats['disk_total']:.1f} GB` ({stats['disk_percent']}%)\n"
                f"• **Sisa Disk**: `{stats['disk_free']:.1f} GB` bebas\n"
                f"• **RAM**: `{stats['ram_used']:.2f}/{stats['ram_total']:.2f} GB` ({stats['ram_percent']}%)\n"
                f"• **Load CPU**: `{stats['load']}`"
            ),
            inline=False,
        )

        # Bagian 3: Ringkasan Cache Disk
        embed.add_field(
            name="📂 Direktori Penyimpanan Bot",
            value=(
                f"• **Dokumen PDF**: `{len(cache['pdf_files'])} file` ({cache['pdf_size'] / (1024*1024):.2f} MB)\n"
                f"• **Gambar Preview Cover**: `{len(cache['thumb_files'])} file` ({cache['thumb_size'] / 1024:.1f} KB)\n"
                f"• **Diagram Pinout**: `{len(cache['pinout_files'])} file` ({cache['pinout_size'] / 1024:.1f} KB)\n"
                f"• **Total Pemakaian Bot**: `{total_cache_mb:.2f} MB`"
            ),
            inline=False,
        )

        embed.set_footer(text="🔄 Auto-refresh aktif tiap 1 menit • Timeout 15 menit")
        return embed

    @discord.ui.button(label="📜 Lihat Isi Disk", style=discord.ButtonStyle.primary, row=0)
    async def btn_list_disk(self, interaction: discord.Interaction, button: discord.ui.Button):
        cache = get_cache_summary()
        if not cache["pdf_files"]:
            await interaction.response.send_message("📂 Folder `downloads/` saat ini kosong (tidak ada file PDF).", ephemeral=True)
            return

        list_view = discord.ui.View(timeout=120)
        list_view.add_item(DeleteFileSelect(cache["pdf_files"]))

        file_lines = []
        for i, (fn, _, sz) in enumerate(cache["pdf_files"][:15], 1):
            sz_s = f"{sz / 1024:.0f} KB" if sz < 1024 * 1024 else f"{sz / 1024 / 1024:.2f} MB"
            file_lines.append(f"`{i}.` **{fn}** (`{sz_s}`)")

        extra = f"\n*...dan {len(cache['pdf_files']) - 15} file lainnya*" if len(cache["pdf_files"]) > 15 else ""

        embed = discord.Embed(
            title=f"📋 Berkas PDF Tersimpan ({len(cache['pdf_files'])} file)",
            description="\n".join(file_lines) + extra + "\n\n*Pilih file dari menu dropdown di bawah untuk menghapusnya:*",
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed, view=list_view, ephemeral=True)

    @discord.ui.button(label="🧹 Hapus Thumbnail & Pinout", style=discord.ButtonStyle.danger, row=0)
    async def btn_clean_temp(self, interaction: discord.Interaction, button: discord.ui.Button):
        thumb_dir = os.path.join(config.DOWNLOAD_DIR, ".thumbnails")
        pinout_dir = os.path.join(config.DOWNLOAD_DIR, ".pinouts")
        count = 0
        cleaned_bytes = 0

        for d in (thumb_dir, pinout_dir):
            if os.path.isdir(d):
                for f in os.listdir(d):
                    p = os.path.join(d, f)
                    if os.path.isfile(p):
                        try:
                            cleaned_bytes += os.path.getsize(p)
                            os.remove(p)
                            count += 1
                        except OSError:
                            pass

        embed = await asyncio.to_thread(self.build_panel_embed)
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(
            f"🧹 Berhasil membersihkan `{count}` file gambar sementara (`{cleaned_bytes / 1024:.1f} KB`).",
            ephemeral=True,
        )

    @discord.ui.button(label="⚡ Sync Command Tree", style=discord.ButtonStyle.success, row=0)
    async def btn_sync_commands(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            synced = await self.bot.tree.sync()
            await interaction.followup.send(
                f"✅ **Sinkronisasi Berhasil!** `{len(synced)}` slash commands telah disinkronkan secara global ke Discord API.",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Gagal melakukan sinkronisasi: {e}", ephemeral=True)


class PanelCog(commands.Cog):
    """Cog slash command panel khusus owner bot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="panel",
        description="Panel kontrol, auto-refresh statistik VPS, dan health check database (Khusus Owner)"
    )
    async def panel(self, interaction: discord.Interaction):
        is_owner = False
        if config.OWNER_ID and interaction.user.id == config.OWNER_ID:
            is_owner = True
        elif not config.OWNER_ID:
            app_info = await self.bot.application_info()
            if interaction.user.id == app_info.owner.id:
                is_owner = True

        if not is_owner:
            await interaction.response.send_message(
                "❌ Akses ditolak. Perintah ini hanya dapat diakses oleh **Owner Bot**.",
                ephemeral=True,
            )
            return

        view = OwnerPanelView(self.bot, interaction.user.id)
        embed = await asyncio.to_thread(view.build_panel_embed)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        message = await interaction.original_response()
        asyncio.create_task(view.start_auto_refresh(message))


async def setup(bot: commands.Bot):
    await bot.add_cog(PanelCog(bot))
