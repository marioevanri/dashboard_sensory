"""
config.py
=========
Konstanta dan konfigurasi bersama untuk dashboard dan ETL.
Import dari file lain: from config import STATUS_ORDER, PARAM_COLS, dll
"""

from pathlib import Path

# ── PATH ─────────────────────────────────────────────────────────
ROOT_DIR   = Path(__file__).parent
RAW_FOLDER = ROOT_DIR / "raw_data" / "sensory_bulanan"
CACHE_FILE = ROOT_DIR / "cache" / "data_cache.parquet"
DB_PATH    = ROOT_DIR / "database" / "qc_sensory.db"

# ── STATUS ───────────────────────────────────────────────────────
STATUS_ORDER = ["TP 2-", "TP 1-", "Pass", "TP 1+", "TP 2+", "TP 3"]

STATUS_COLORS = {
    "TP 2-": "#8B0000",
    "TP 1-": "#D85A30",
    "Pass":  "#2E8B57",
    "TP 1+": "#4DA6FF",
    "TP 2+": "#1565C0",
    "TP 3":  "#0D0D5C",
}

STATUS_NUM = {
    "TP 2-": -2,
    "TP 1-": -1,
    "Pass":   0,
    "TP 1+":  1,
    "TP 2+":  2,
    "TP 3":   3,
}

# Status yang dianggap Not Pass (perlu Triangle Test)
CRITICAL_STATUS = {"TP 2-", "TP 2+", "TP 3"}

# ── PARAMETER SENSORY ────────────────────────────────────────────
PARAM_COLS = [
    "Odor", "Coffee_Aroma", "Creamy", "Milky",
    "Mouthfeel", "Sweet", "Taste_Profile",
]

PARAM_LABELS = {
    "Odor":          "Odor",
    "Coffee_Aroma":  "Coffee Aroma",
    "Creamy":        "Creamy",
    "Milky":         "Milky",
    "Mouthfeel":     "Mouthfeel",
    "Sweet":         "Sweet",
    "Taste_Profile": "Taste Profile",
}

# ── PLANT ────────────────────────────────────────────────────────
PLANT_OPTIONS = ["Plant 1", "Plant 2", "Blending", "Unknown"]

PLANT_SUFFIX_MAP = {
    "AA": "Plant 1",
    "AC": "Plant 2",
    "AE": "Plant 2",
    "AB": "Blending",
    "BB": "Blending",
}

# ── SHIFT ────────────────────────────────────────────────────────
SHIFT_ORDER = ["1", "1-2", "2", "2-3", "3"]

# ── COMPARISON ───────────────────────────────────────────────────
COMPARISON_VALUES = {"MATCH", "MISMATCH", "NO_VERIFICATION"}

# ── BUSINESS RULES ───────────────────────────────────────────────
# Minimum sample untuk masuk perhitungan (hindari noise data kecil)
MIN_SAMPLE_FILTER = 5

# Coverage target verifikasi (%)
COVERAGE_TARGET = 80.0
