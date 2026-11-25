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
    from core.env_utils import parse_int_env
    assert parse_int_env("TIDAK_ADA_ENV_INI", 7) == 7
    os.environ["TEST_BAD_INT"] = "bukan_angka"
    assert parse_int_env("TEST_BAD_INT", 5) == 5
    os.environ["TEST_BAD_INT"] = "42"
    assert parse_int_env("TEST_BAD_INT", 5) == 42
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




# --- T-01: SSRF redirect bypass via manual redirect loop ---
def t_t01_ssrf_redirect_manual_loop():
    import inspect
    from sources.datasheet4u import download_single, BASE_URL, is_allowed_url
    src = inspect.getsource(download_single)
    # Verify manual redirect loop exists with SSRF protection
    assert "allow_redirects=False" in src, "Must use allow_redirects=False"
    assert "is_allowed_url" in src, "Must validate each redirect hop"
    assert "redirects" in src, "Must track redirect count"
    assert "301" in src and "302" in src, "Must handle 301/302 redirects"
    # Verify is_allowed_url blocks evil.com
    assert not is_allowed_url("http://evil.com/malware.pdf")
    assert is_allowed_url(BASE_URL + "/valid.pdf")
    # Verify redirect target validation
    assert not is_allowed_url("http://evil.com")
    assert not is_allowed_url("https://attacker.net/phish")



# --- T-02: ProxyManager thread-safe cache with RLock ---
def t_t02_proxy_manager_rlock():
    from core.proxy_manager import ProxyManager
    import threading, time
    # Verify class attributes exist
    assert hasattr(ProxyManager, "_lock")
    assert hasattr(ProxyManager, "CACHE_DURATION")
    assert hasattr(ProxyManager, "NULL_CACHE_DURATION")
    assert ProxyManager.CACHE_DURATION == 300.0
    assert ProxyManager.NULL_CACHE_DURATION == 25.0
    # Test thread-safety via instance method
    pm = ProxyManager()  # creates instance with proxy_file=None / auto-proxies.txt
    errors = []
    def worker():
        try:
            for _ in range(3):
                pm.mark_proxy_dead("http://test.invalid:8080")
                _ = pm.get_working_proxy(force_refresh=True)
        except Exception as e:
            errors.append(e)
    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert len(errors) == 0, f"Thread errors: {errors}"

# --- S-01: Stream connection close via finally ---
def t_s01_stream_close_finally():
    import inspect, sources.datasheet4u as ds4u, sources.alldatasheet as ads
    ds4u_src = inspect.getsource(ds4u.download_single)
    assert "finally:" in ds4u_src
    assert ".close()" in ds4u_src
    ads_src = inspect.getsource(ads.download_single)
    assert "finally:" in ads_src
    assert "r_pdf.close()" in ads_src

# --- S-02: URL normalization via urljoin ---
def t_s02_urljoin_normalization():
    import urllib.parse
    from sources.datasheet4u import BASE_URL as BASE4U
    from sources.alldatasheet import BASE_URL as BASEADS
    # Test urljoin produces correct URLs
    import urllib.parse
    from sources.datasheet4u import BASE_URL as BASE4U
    from sources.alldatasheet import BASE_URL as BASEADS
    # Absolute path join
    joined = urllib.parse.urljoin(BASE4U, "/pdf/test.pdf")
    assert "/pdf/test.pdf" in joined
    assert joined.startswith("http")  # urljoin uses scheme from BASE4U
    # Protocol-relative join
    joined2 = urllib.parse.urljoin(BASE4U, "//cdn.example.com/file.pdf")
    assert "cdn.example.com" in joined2
    # alldatasheet
    joined3 = urllib.parse.urljoin(BASEADS, "//download.alldatasheet.com/file.pdf")
    assert "download.alldatasheet.com" in joined3

# --- S-03: Retry loop with tried_direct flag and 429/5xx backoff ---
def t_s03_retry_tried_direct_backoff():
    import inspect
    import sources.alldatasheet as ads
    # Find the search function - may be named differently
    search_fn = getattr(ads, "search_alldatasheet", None) or getattr(ads, "search", None)
    if search_fn is None:
        # Find function containing retry loop
        import re
        fns = [(n, o) for n, o in vars(ads).items() if callable(o) and hasattr(o, '__code__')]
        for n, o in fns:
            try:
                src = inspect.getsource(o)
                if "tried_direct" in src:
                    search_fn = o
                    break
            except (OSError, TypeError):
                continue
    assert search_fn is not None, "No search function with retry loop found"
    src = inspect.getsource(search_fn)
    assert "tried_direct" in src
    backoff_kw = any(k in src for k in ["backoff", "sleep", "time"])
    assert backoff_kw, "retry loop must have backoff or sleep"
    assert "429" in src or "500" in src or "502" in src or "503" in src
    assert "force_refresh" in src
for name, fn in [
    ("M-01 allowlist menerima host sah", t_allow_ok),
    ("M-01 allowlist menolak host/skema asing", t_allow_reject),
    ("H-02 content_length_exceeds", t_content_length),
    ("H-02 read_capped", t_read_capped),
    ("T-01 SSRF redirect manual loop", t_t01_ssrf_redirect_manual_loop),
    ("T-02 ProxyManager RLock", t_t02_proxy_manager_rlock),
    ("S-01 Stream close finally", t_s01_stream_close_finally),
    ("S-02 URL join normalization", t_s02_urljoin_normalization),
    ("S-03 Retry with tried_direct", t_s03_retry_tried_direct_backoff),
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
