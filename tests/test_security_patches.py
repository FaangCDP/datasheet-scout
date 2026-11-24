"""
tests/test_security_patches.py -- Verifikasi patch keamanan (H-01..L-06).

Jalankan: ./venv/bin/python tests/test_security_patches.py
Tanpa framework: assert murni, exit code 1 jika ada yang gagal.
"""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import pdf_fetch
from sources import alldatasheet, datasheet4u
from bots.discord import config
from bots.discord.guards import prune_cache, handle_cooldown
from bots.discord.cogs.datasheet_cog import _safe_text, DatasheetCog
from bots.discord.cogs import pinout_cog, random_cog, panel_cog
from batch_download_http import folder_size_mb, MAX_TOTAL_MB

checks = []


def check(name, fn):
    try:
        fn()
        checks.append((name, True, ""))
    except AssertionError as e:
        checks.append((name, False, str(e) or "assert gagal"))
    except Exception as e:
        checks.append((name, False, f"{type(e).__name__}: {e}"))


# --- H-02 / M-01: allowlist host ---
def t_allow_ok():
    assert alldatasheet.is_allowed_url("https://www.alldatasheet.com/view.jsp?Searchword=NE555")
    assert alldatasheet.is_allowed_url("https://alldatasheet.com/x.pdf")
    assert alldatasheet.is_allowed_url("https://pdf1.alldatasheet.com/datasheet-pdf/view/123/x.pdf")
    assert datasheet4u.is_allowed_url("https://www.datasheet4u.com/datasheet-pdf/NE555.pdf")
    assert datasheet4u.is_allowed_url("https://datasheet4u.com/a.pdf")


def t_allow_reject():
    bad = [
        "http://www.alldatasheet.com/x.pdf",        # bukan https
        "https://evil.com/x.pdf",                   # host asing
        "https://alldatasheet.com.evil.com/x.pdf",  # suffix palsu
        "https://169.254.169.254/latest/meta-data/",# metadata cloud
        "https://127.0.0.1/x.pdf",
        "//alldatasheet.com/x.pdf",                 # skema kosong
        "",
        None,
    ]
    for u in bad:
        assert not alldatasheet.is_allowed_url(u), f"lolos: {u!r}"
        assert not datasheet4u.is_allowed_url(u), f"lolos: {u!r}"


# --- H-02: cap ukuran ---
class FakeResp:
    def __init__(self, body=b"", headers=None):
        self._body = body
        self.headers = headers or {}

    def iter_content(self, chunk_size=65536):
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i:i + chunk_size]


def t_content_length():
    assert pdf_fetch.content_length_exceeds(FakeResp(headers={"Content-Length": str(10**9)}))
    assert not pdf_fetch.content_length_exceeds(FakeResp(headers={"Content-Length": "100"}))
    assert not pdf_fetch.content_length_exceeds(FakeResp())


def t_read_capped():
    assert pdf_fetch.read_capped(FakeResp(b"%PDF-1.7 hello")) == b"%PDF-1.7 hello"
    assert pdf_fetch.read_capped(FakeResp(b"")) is None
    assert pdf_fetch.read_capped(FakeResp(b"x" * 5000), limit=1000) is None


def t_write_capped():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "a.pdf")
        n = pdf_fetch.write_capped(iter([b"world"]), p, initial=b"hello ")
        assert n == 11, n
        assert open(p, "rb").read() == b"hello world"

        p2 = os.path.join(d, "b.pdf")
        assert pdf_fetch.write_capped(iter([b"y" * 5000]), p2, initial=b"%PDF-", limit=1000) is None
        assert not os.path.exists(p2), "file melebihi batas harus dihapus"


def t_too_large():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "big.pdf")
        with open(p, "wb") as f:
            f.write(b"x" * 2048)
        assert not pdf_fetch.too_large_to_parse(p)
        assert pdf_fetch.too_large_to_parse(p, limit=1024)
        assert pdf_fetch.too_large_to_parse(os.path.join(d, "missing.pdf"))


# --- L-01: parse ENV aman ---
def t_int_env():
    assert config._int_env("TIDAK_ADA_ENV_INI", 7) == 7
    os.environ["TEST_BAD_INT"] = "bukan_angka"
    assert config._int_env("TEST_BAD_INT", 5) == 5
    os.environ["TEST_BAD_INT"] = "42"
    assert config._int_env("TEST_BAD_INT", 5) == 42
    del os.environ["TEST_BAD_INT"]


# --- L-04: escape markdown + strip URL ---
def t_safe_text():
    out = _safe_text("Lihat [klik](https://evil.com/x) **gratis**")
    assert "https://evil.com" not in out, out
    assert "**gratis**" not in out, out
    assert "tautan" in out
    assert len(_safe_text("a" * 5000, 100)) == 100


# --- H-01: cooldown terpasang ---
def t_cooldowns():
    # app_commands cooldown == check predicate, jadi buktinya `checks` tidak kosong
    for cmd, label in (
        (DatasheetCog.datasheet, "/datasheet"),
        (pinout_cog.PinoutCog.pinout, "/pinout"),
        (random_cog.RandomCog.random_cmd, "/random"),
    ):
        assert cmd.checks, f"cooldown {label} hilang"


def t_view_guards():
    from bots.discord.cogs.datasheet_cog import PackageSelectionView, CatalogPaginationView
    from bots.discord.cogs.random_cog import RandomComponentView
    for cls in (PackageSelectionView, CatalogPaginationView, RandomComponentView):
        assert hasattr(cls, "interaction_check"), f"{cls.__name__} tanpa interaction_check"
    assert hasattr(panel_cog, "OwnerOnlyView")
    assert hasattr(panel_cog.OwnerOnlyView, "interaction_check")


def t_guards_module():
    assert callable(prune_cache) and callable(handle_cooldown)


# --- H-01: kuota batch CLI ---
def t_quota():
    assert MAX_TOTAL_MB > 0
    with tempfile.TemporaryDirectory() as d:
        assert folder_size_mb(d) == 0
        with open(os.path.join(d, "f.bin"), "wb") as f:
            f.write(b"x" * (1024 * 1024))
        assert 0.9 < folder_size_mb(d) < 1.1


# --- L-06: extractor menolak PDF raksasa ---
def t_extractors_cap():
    from core.specs_extractor import extract_key_specs
    from core.preview_extractor import extract_pdf_thumbnail
    from core.pinout_extractor import extract_pinout_image
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "huge.pdf")
        with open(p, "wb") as f:
            f.write(b"%PDF-1.7" + b"0" * (pdf_fetch.MAX_PARSE_BYTES + 10))
        assert extract_key_specs(p) == {}
        assert extract_pdf_thumbnail(p) is None
        assert extract_pinout_image(p) == (None, None)


for name, fn in [
    ("M-01 allowlist menerima host sah", t_allow_ok),
    ("M-01 allowlist menolak host/skema asing", t_allow_reject),
    ("H-02 content_length_exceeds", t_content_length),
    ("H-02 read_capped", t_read_capped),
    ("H-02 write_capped + hapus saat lewat batas", t_write_capped),
    ("L-06 too_large_to_parse", t_too_large),
    ("L-01 _int_env aman", t_int_env),
    ("L-04 _safe_text escape + strip URL", t_safe_text),
    ("H-01 cooldown terpasang", t_cooldowns),
    ("L-03 interaction_check semua View", t_view_guards),
    ("H-01 guards module", t_guards_module),
    ("H-01 kuota batch CLI", t_quota),
    ("L-06 extractor menolak PDF raksasa", t_extractors_cap),
]:
    check(name, fn)

gagal = [c for c in checks if not c[1]]
for name, ok, err in checks:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -> {err}" if err else ""))
print(f"\n{len(checks) - len(gagal)}/{len(checks)} lulus")
sys.exit(1 if gagal else 0)
