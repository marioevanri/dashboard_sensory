"""
tests/test_load_data.py
=======================
Unit test untuk fungsi-fungsi di load_data.py

Jalankan: pytest tests/
"""

import pytest
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard"))
from load_data import (
    get_plant, standardize_status, infer_direction,
    norm_analyst_no,
)


# ── get_plant ────────────────────────────────────────────────────

class TestGetPlant:
    def test_plant1_suffix_aa(self):
        assert get_plant("25010116AA") == "Plant 1"

    def test_plant2_suffix_ae(self):
        assert get_plant("25010116AE") == "Plant 2"

    def test_plant2_suffix_ac(self):
        assert get_plant("25010116AC") == "Plant 2"

    def test_blending_suffix_ab(self):
        assert get_plant("25010116AB") == "Blending"

    def test_blending_suffix_bb(self):
        assert get_plant("250101Y9BB") == "Blending"

    def test_unknown_suffix(self):
        assert get_plant("25010116XZ") == "Unknown"

    def test_nan_returns_unknown(self):
        assert get_plant(None) == "Unknown"
        assert get_plant(float("nan")) == "Unknown"


# ── standardize_status ───────────────────────────────────────────

class TestStandardizeStatus:
    def test_pass_variations(self):
        assert standardize_status("PASS") == "Pass"
        assert standardize_status("pass") == "Pass"

    def test_tp1_minus(self):
        assert standardize_status("TP1-")   == "TP 1-"
        assert standardize_status("TP 1-")  == "TP 1-"
        assert standardize_status("TP 1 -") == "TP 1-"

    def test_tp1_plus(self):
        assert standardize_status("TP1+")   == "TP 1+"
        assert standardize_status("TP 1+")  == "TP 1+"
        assert standardize_status("TP 1 +") == "TP 1+"

    def test_tp2_minus(self):
        assert standardize_status("TP2-")   == "TP 2-"
        assert standardize_status("TP  2-") == "TP 2-"

    def test_tp3(self):
        assert standardize_status("TP 3")   == "TP 3"
        assert standardize_status("TP3")    == "TP 3"

    def test_empty_returns_none(self):
        assert standardize_status("") is None
        assert standardize_status("0") is None
        assert standardize_status(None) is None

    def test_nan_returns_none(self):
        assert standardize_status(float("nan")) is None


# ── infer_direction ──────────────────────────────────────────────

class TestInferDirection:
    def test_pass_unchanged(self):
        assert infer_direction("Pass", "Kurang creamy") == "Pass"

    def test_tp1_kurang_becomes_minus(self):
        assert infer_direction("TP 1", "Kurang milky") == "TP 1-"

    def test_tp1_lebih_becomes_plus(self):
        assert infer_direction("TP 1", "Lebih creamy") == "TP 1+"

    def test_tp2_kurang_becomes_minus(self):
        assert infer_direction("TP 2", "Agak kurang creamy") == "TP 2-"

    def test_tp1_minus_unchanged(self):
        """Status yang sudah punya arah tidak berubah."""
        assert infer_direction("TP 1-", "Lebih creamy") == "TP 1-"

    def test_no_remark_unchanged(self):
        assert infer_direction("TP 1", None) == "TP 1"
        assert infer_direction("TP 1", "")   == "TP 1"

    def test_tp3_unchanged(self):
        assert infer_direction("TP 3", "Kurang milky") == "TP 3"

    def test_none_status_returns_none(self):
        assert infer_direction(None, "Kurang milky") is None


# ── norm_analyst_no ──────────────────────────────────────────────

class TestNormAnalystNo:
    def test_int_string(self):
        assert norm_analyst_no("1") == 1
        assert norm_analyst_no("2") == 2
        assert norm_analyst_no("3") == 3

    def test_float_string(self):
        assert norm_analyst_no("1.0") == 1

    def test_invalid_returns_none(self):
        assert norm_analyst_no("abc") is None
        assert norm_analyst_no(None) is None
        assert norm_analyst_no("") is None


# ── classify_gap (dari tab2_gap.py) ─────────────────────────────

class TestClassifyGap:
    def setup_method(self):
        sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard" / "tabs"))
        from tab2_gap import classify_gap
        self.classify_gap = classify_gap

    def test_match_returns_none(self):
        assert self.classify_gap("Pass", "Pass") is None
        assert self.classify_gap("TP 1-", "TP 1-") is None

    def test_beda_intensitas(self):
        # Via Pass — berapapun jaraknya
        assert self.classify_gap("Pass", "TP 1-") == "Beda Intensitas"
        assert self.classify_gap("Pass", "TP 2-") == "Beda Intensitas"
        assert self.classify_gap("Pass", "TP 1+") == "Beda Intensitas"
        assert self.classify_gap("Pass", "TP 2+") == "Beda Intensitas"
        # Sama arah — jarak 1
        assert self.classify_gap("TP 1-", "TP 2-") == "Beda Intensitas"
        assert self.classify_gap("TP 1+", "TP 2+") == "Beda Intensitas"
        # Sama arah — jarak 2
        assert self.classify_gap("TP 1-", "TP 2-") == "Beda Intensitas"

    def test_beda_arah(self):
        # Berlawanan tanda
        assert self.classify_gap("TP 1-", "TP 1+") == "Beda Arah"
        assert self.classify_gap("TP 2-", "TP 1+") == "Beda Arah"
        assert self.classify_gap("TP 1-", "TP 2+") == "Beda Arah"
        assert self.classify_gap("TP 2-", "TP 2+") == "Beda Arah"

    def test_tp3_kategori_sendiri(self):
        assert self.classify_gap("Pass",  "TP 3")  == "Melibatkan TP 3"
        assert self.classify_gap("TP 3",  "Pass")  == "Melibatkan TP 3"
        assert self.classify_gap("TP 1-", "TP 3")  == "Melibatkan TP 3"
        assert self.classify_gap("TP 3",  "TP 1+") == "Melibatkan TP 3"
        # TP 3 vs TP 3 = match → None
        assert self.classify_gap("TP 3",  "TP 3")  is None

    def test_tp3_tidak_masuk_beda_arah(self):
        """TP 3 tidak punya arah, tidak boleh masuk Beda Arah."""
        result = self.classify_gap("TP 1-", "TP 3")
        assert result == "Melibatkan TP 3"
        assert result != "Beda Arah"
