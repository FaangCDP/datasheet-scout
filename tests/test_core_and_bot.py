"""
tests/test_core_and_bot.py -- Comprehensive Unit Tests for Core & Bot Modules
Tests package classification, specs extraction, relevance ranking, and Discord cogs.
"""

import asyncio
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.package_classifier import (
    clean_base_component,
    detect_package_from_item,
    select_distinct_packages,
)
from core.pinout_extractor import find_pinout_page
from core.scraper import compute_relevance
from core.specs_extractor import extract_key_specs


class TestPackageClassifier(unittest.TestCase):
    """Test package classifier functions and suffix stripping."""

    def test_clean_base_component_suffixes(self):
        cases = [
            ("LM358D", "LM358"),
            ("LM358DR", "LM358"),
            ("LM358N", "LM358"),
            ("LM358-N", "LM358"),
            ("NE555P", "NE555"),
            ("ATMEGA328P-PU", "ATMEGA328P"),
            ("TL072CD", "TL072C"),
            ("Arduino Uno", "Arduino Uno"),
            ("BC547B", "BC547B"),  # B is hFE gain grade, not package
        ]
        for input_name, expected in cases:
            with self.subTest(input_name=input_name):
                self.assertEqual(clean_base_component(input_name), expected)

    def test_detect_package_explicit(self):
        item_dip = {"part_no": "LM358", "description": "Dual Op-Amp in 8-pin DIP package"}
        self.assertEqual(detect_package_from_item(item_dip), "DIP")

        item_soic = {"part_no": "LM358", "description": "Dual Op-Amp in SOIC-8"}
        self.assertEqual(detect_package_from_item(item_soic), "SOIC")

        item_to220 = {"part_no": "LM7805", "description": "3-Terminal Positive Regulator TO-220"}
        self.assertEqual(detect_package_from_item(item_to220), "TO-220")

    def test_detect_package_suffix(self):
        self.assertEqual(detect_package_from_item({"part_no": "LM358AP", "description": ""}), "DIP")
        self.assertEqual(detect_package_from_item({"part_no": "LM358DT", "description": ""}), "SOIC")
        self.assertEqual(detect_package_from_item({"part_no": "LM358APT", "description": ""}), "TSSOP")
        self.assertEqual(detect_package_from_item({"part_no": "LM358QT", "description": ""}), "QFN")

    def test_select_distinct_packages(self):
        candidates = [
            {"part_no": "LM358N", "description": ""},    # DIP
            {"part_no": "LM358P", "description": ""},    # DIP (duplicate package)
            {"part_no": "LM358D", "description": ""},    # SOIC
            {"part_no": "LM358DT", "description": ""},   # SOIC (duplicate package)
            {"part_no": "LM358APT", "description": ""},  # TSSOP
            {"part_no": "LM358QT", "description": ""},   # QFN
        ]
        distinct = select_distinct_packages(candidates, max_items=5)
        self.assertIn("DIP", distinct)
        self.assertIn("SOIC", distinct)
        self.assertIn("TSSOP", distinct)
        self.assertIn("QFN", distinct)
        # Verify deduplication
        self.assertEqual(len(distinct), 4)


class TestSpecsExtractor(unittest.TestCase):
    """Test regex specification parsing on mock text bodies."""

    @patch("core.specs_extractor.subprocess.run")
    def test_extract_specs_comprehensive(self, mock_subproc):
        mock_output = """
        LM158, LM258, LM358 Dual Operational Amplifiers
        Features:
        - Wide supply range of 3V to 36V for battery systems
        - Unity-gain bandwidth: 1.2 MHz CPU clock
        - Available in SOIC-8, TSSOP-8, and SOT-23 packages
        - Operating temperature range: -40°C to +85°C
        """
        mock_res = MagicMock()
        mock_res.stdout = mock_output
        mock_subproc.return_value = mock_res

        with patch("os.path.isfile", return_value=True):
            specs = extract_key_specs("/fake/path.pdf")

        self.assertEqual(specs.get("Tegangan Kerja"), "3V to 36V")
        self.assertEqual(specs.get("Frekuensi/Clock"), "1.2 MHz")
        self.assertIn("SOIC", specs.get("Kemasan/Package", ""))
        self.assertEqual(specs.get("Suhu Operasi"), "-40°C to +85°C")

    @patch("core.specs_extractor.subprocess.run")
    def test_extract_specs_empty(self, mock_subproc):
        mock_res = MagicMock()
        mock_res.stdout = "No technical information here."
        mock_subproc.return_value = mock_res

        with patch("os.path.isfile", return_value=True):
            specs = extract_key_specs("/fake/path.pdf")

        self.assertEqual(specs, {})


class TestPinoutExtractor(unittest.TestCase):
    """Test pinout page detection heuristics."""

    @patch("core.pinout_extractor.subprocess.run")
    def test_find_pinout_page_detection(self, mock_subproc):
        def side_effect(cmd, **kwargs):
            res = MagicMock()
            cmd_str = " ".join(cmd)
            if "pdfinfo" in cmd[0]:
                res.stdout = "Pages: 5\n"
            elif "-f" in cmd:
                page_idx = cmd[cmd.index("-f") + 1]
                if page_idx == "2":
                    res.stdout = "PIN CONFIGURATION AND FUNCTIONS (Top View)\nPin 1: VCC\nPin 2: GND"
                else:
                    res.stdout = "Introduction and overview text."
            return res

        mock_subproc.side_effect = side_effect
        with patch("core.pinout_extractor.HAS_PYPDFIUM", False):
            detected_page = find_pinout_page("/fake/doc.pdf", max_pages=5)
        self.assertEqual(detected_page, 2)


class TestRelevanceRanking(unittest.TestCase):
    """Test part number scoring and disambiguation."""

    def test_exact_match(self):
        score = compute_relevance({"part_no": "LM358"}, "LM358")
        self.assertEqual(score, 100.0)

    def test_prefix_match(self):
        score = compute_relevance({"part_no": "LM358AP"}, "LM358")
        self.assertEqual(score, 80.0)

    def test_uno_vs_nano_disambiguation(self):
        score_uno = compute_relevance({"part_no": "ARDUINO-UNO"}, "Arduino Uno")
        score_nano = compute_relevance({"part_no": "ARDUINO-NANO"}, "Arduino Uno")
        self.assertGreater(score_uno, score_nano)

    def test_unrelated_component(self):
        score = compute_relevance({"part_no": "PF92251B1-000U-S99"}, "Uno")
        self.assertEqual(score, 0.0)


class TestDiscordBotCogs(unittest.TestCase):
    """Test Discord bot command registrations, parameters, and autocomplete."""

    def setUp(self):
        from bots.discord.bot import DatasheetBot
        self.bot = DatasheetBot()

    def test_all_cogs_loaded(self):
        async def run_setup():
            await self.bot.setup_hook()
            commands = sorted([c.name for c in self.bot.tree.get_commands()])
            return commands

        commands = asyncio.run(run_setup())
        expected = ["datasheet", "help", "info", "myid", "panel", "ping", "pinout", "purge"]
        for exp in expected:
            self.assertIn(exp, commands)

    def test_datasheet_command_parameters(self):
        async def check_params():
            await self.bot.setup_hook()
            cmd = self.bot.tree.get_command("datasheet")
            params = {p.name: p for p in cmd.parameters}
            return params

        params = asyncio.run(check_params())
        self.assertIn("komponen", params)
        self.assertTrue(params["komponen"].required)
        self.assertIn("kemasan", params)
        self.assertFalse(params["kemasan"].required)
        self.assertIn("pilihan_kemasan", params)
        self.assertFalse(params["pilihan_kemasan"].required)

    def test_in_memory_autocomplete(self):
        async def run_auto():
            await self.bot.setup_hook()
            cog = self.bot.get_cog("DatasheetCog")
            # Test empty query (should return 25 items without error)
            res_empty = await cog.komponen_autocomplete(None, "")
            # Test prefix query
            res_atm = await cog.komponen_autocomplete(None, "atm")
            names_atm = [c.name for c in res_atm]
            return len(res_empty), names_atm

        count_empty, names_atm = asyncio.run(run_auto())
        self.assertEqual(count_empty, 25)
        self.assertIn("ATmega328P", names_atm)


if __name__ == "__main__":
    unittest.main()
