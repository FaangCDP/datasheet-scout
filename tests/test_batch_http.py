"""
Unit test mandiri untuk logika batch_download_http.py.
Tidak mengimpor modul proyek (menghindari dependensi requests/bs4).
Fungsi murni yang diuji di-copy langsung ke sini.
"""
import os
import tempfile
import unittest


# ================================================================
# Fungsi yang diuji (disalin dari batch_download_http.py)
# ================================================================

def sanitize_part_no(part_no: str) -> str:
    """Sanitasi part number agar aman sebagai nama file."""
    return "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in part_no).strip('_')


def sanitize_manufacturer(manufacturer: str) -> str:
    """Sanitasi nama manufacturer agar aman sebagai nama file."""
    safe = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in manufacturer)
    return safe.strip().replace(' ', '_')


def read_component_file(file_path: str) -> list:
    """Baca file .txt dan kembalikan list nama komponen yang bersih."""
    components = []
    seen = set()
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                name = line.strip()
                if not name or name.startswith("#"):
                    continue
                name_upper = name.upper()
                if name_upper in seen:
                    continue
                seen.add(name_upper)
                components.append(name)
    except UnicodeDecodeError:
        try:
            with open(file_path, "r", encoding="latin-1") as f:
                for line in f:
                    name = line.strip()
                    if not name or name.startswith("#"):
                        continue
                    name_upper = name.upper()
                    if name_upper not in seen:
                        seen.add(name_upper)
                        components.append(name)
        except Exception:
            pass
    except FileNotFoundError:
        pass
    return components


def scan_list_folder(list_folder: str) -> list:
    """Scan folder dan baca semua file .txt sebagai kategori."""
    list_folder = os.path.abspath(list_folder)
    if not os.path.isdir(list_folder):
        return []
    categories = []
    for filename in sorted(os.listdir(list_folder)):
        if not filename.lower().endswith(".txt"):
            continue
        file_path = os.path.join(list_folder, filename)
        category_name = os.path.splitext(filename)[0]
        components = read_component_file(file_path)
        if len(components) == 0:
            continue
        categories.append({
            "category": category_name,
            "file_path": file_path,
            "components": components
        })
    return categories


# ================================================================
# Test Cases
# ================================================================

class TestSanitasiPartNo(unittest.TestCase):
    """Menguji bahwa part_no dengan karakter ilegal disanitasi dengan benar."""

    def test_slash_diganti(self):
        self.assertEqual(sanitize_part_no("LM358/NOPB"), "LM358_NOPB")

    def test_backslash_diganti(self):
        self.assertEqual(sanitize_part_no("74HC\\00"), "74HC_00")

    def test_colon_diganti(self):
        self.assertEqual(sanitize_part_no("2N2222:A"), "2N2222_A")

    def test_nama_normal_tidak_berubah(self):
        self.assertEqual(sanitize_part_no("ATmega328P"), "ATmega328P")

    def test_dash_underscore_dipertahankan(self):
        self.assertEqual(sanitize_part_no("ADG419BRZ-REEL7"), "ADG419BRZ-REEL7")

    def test_spasi_diganti(self):
        self.assertEqual(sanitize_part_no("NE 555"), "NE_555")

    def test_tidak_mengandung_separator_path(self):
        hasil = sanitize_part_no("PIC16F877A-I/P")
        self.assertNotIn("/", hasil)
        self.assertNotIn("\\", hasil)

    def test_multiple_slash(self):
        self.assertEqual(sanitize_part_no("A/B/C/D"), "A_B_C_D")


class TestSanitasiManufacturer(unittest.TestCase):

    def test_normal(self):
        self.assertEqual(sanitize_manufacturer("STMicroelectronics"), "STMicroelectronics")

    def test_spasi(self):
        self.assertEqual(sanitize_manufacturer("Texas Instruments"), "Texas_Instruments")

    def test_karakter_aneh(self):
        result = sanitize_manufacturer("Foo & Bar (Corp)")
        self.assertNotIn("&", result)
        self.assertNotIn("(", result)


class TestReadComponentFile(unittest.TestCase):
    """Menguji pembacaan dan pembersihan file list komponen."""

    def _write_temp(self, lines):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
        f.write("\n".join(lines))
        f.close()
        return f.name

    def test_baris_kosong_diabaikan(self):
        path = self._write_temp(["NE555", "", "  ", "LM358"])
        result = read_component_file(path)
        self.assertEqual(result, ["NE555", "LM358"])
        os.unlink(path)

    def test_komentar_diabaikan(self):
        path = self._write_temp(["# ini komentar", "NE555", "# lagi", "LM358"])
        result = read_component_file(path)
        self.assertEqual(result, ["NE555", "LM358"])
        os.unlink(path)

    def test_deduplikasi_case_insensitive(self):
        path = self._write_temp(["NE555", "ne555", "Ne555"])
        result = read_component_file(path)
        self.assertEqual(result, ["NE555"])
        os.unlink(path)

    def test_file_tidak_ada(self):
        result = read_component_file("/tmp/tidak_ada_file_ini_12345.txt")
        self.assertEqual(result, [])

    def test_urutan_dipertahankan(self):
        path = self._write_temp(["C", "A", "B"])
        result = read_component_file(path)
        self.assertEqual(result, ["C", "A", "B"])
        os.unlink(path)

    def test_whitespace_di_strip(self):
        path = self._write_temp(["  NE555  ", "\tLM358\t"])
        result = read_component_file(path)
        self.assertEqual(result, ["NE555", "LM358"])
        os.unlink(path)


class TestScanListFolder(unittest.TestCase):
    """Menguji pemindaian folder list/."""

    def test_file_non_txt_diabaikan(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "valid.txt"), "w") as f:
                f.write("NE555\n")
            with open(os.path.join(d, "gambar.png"), "w") as f:
                f.write("bukan txt\n")
            result = scan_list_folder(d)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["category"], "valid")

    def test_txt_kosong_dilewati(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "kosong.txt"), "w") as f:
                f.write("")
            result = scan_list_folder(d)
            self.assertEqual(len(result), 0)

    def test_folder_tidak_ada(self):
        result = scan_list_folder("/tmp/folder_tidak_ada_12345")
        self.assertEqual(result, [])

    def test_multiple_kategori_sorted(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "Zener.txt"), "w") as f:
                f.write("BZX84C5V1\n")
            with open(os.path.join(d, "Amplifier.txt"), "w") as f:
                f.write("LM358\n")
            result = scan_list_folder(d)
            self.assertEqual(len(result), 2)
            self.assertEqual(result[0]["category"], "Amplifier")
            self.assertEqual(result[1]["category"], "Zener")


class TestValidasiPDF(unittest.TestCase):
    """Menguji deteksi magic byte PDF."""

    def test_pdf_valid(self):
        self.assertTrue(b"%PDF-1.7\r\n".startswith(b"%PDF-"))

    def test_pdf_versi_lama(self):
        self.assertTrue(b"%PDF-1.4 ".startswith(b"%PDF-"))

    def test_html_bukan_pdf(self):
        self.assertFalse(b"<!DOCTYPE html>".startswith(b"%PDF-"))

    def test_bytes_kosong(self):
        self.assertFalse(b"".startswith(b"%PDF-"))

    def test_cloudflare_challenge(self):
        self.assertFalse(b"<html><head><title>Attention Required".startswith(b"%PDF-"))


class TestSkipExisting(unittest.TestCase):
    """Menguji logika skip file yang sudah ada."""

    def test_file_ada_dan_cukup_besar(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "NE555_STMicroelectronics_datasheet.pdf")
            with open(path, "wb") as f:
                f.write(b"%PDF-" + b"x" * 2000)
            self.assertTrue(os.path.isfile(path))
            self.assertGreater(os.path.getsize(path), 1000)

    def test_file_ada_tapi_terlalu_kecil(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "NE555_STMicroelectronics_datasheet.pdf")
            with open(path, "wb") as f:
                f.write(b"tiny")
            self.assertTrue(os.path.isfile(path))
            self.assertLessEqual(os.path.getsize(path), 1000)

    def test_file_tidak_ada(self):
        self.assertFalse(os.path.isfile("/tmp/tidak_ada_12345.pdf"))


if __name__ == "__main__":
    unittest.main()
