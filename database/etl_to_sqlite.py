"""
etl_to_sqlite.py
================
ETL pipeline: Excel Sensory → clean → simpan ke SQLite.

Tabel: sensory_clean (1 tabel flat, 1 baris per Batch + Mix/IBC)
Primary Key: no_batch + mix_ibc

Cara pakai:
    python database/etl_to_sqlite.py

Output:
    database/qc_sensory.db
"""

import sys
import sqlite3
import pandas as pd
from pathlib import Path

# ── CONFIG ───────────────────────────────────────────────────────
_HERE      = Path(__file__).parent
_ROOT      = _HERE.parent  # root project (berisi config.py)
DB_PATH    = _HERE / "qc_sensory.db"
RAW_FOLDER = _ROOT / "raw_data" / "sensory_bulanan"

# Tambahkan folder dashboard ke path supaya bisa import load_data
for _p in [str(_ROOT / "dashboard"), str(_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _load_data(raw_folder):
    """Import load_all dari dashboard/load_data.py dan jalankan."""
    from load_data import load_all  # import di dalam fungsi — tidak trigger Pylance warning
    return load_all(raw_folder)

SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS sensory_clean (
    -- Identitas batch
    no_batch         TEXT NOT NULL,
    mix_ibc          TEXT NOT NULL,
    tgl_analisa      TEXT,
    produk_grade     TEXT,
    shift            TEXT,
    plant            TEXT,

    -- Hasil tiap analis KimFis
    a1_nama          TEXT,
    a1_status        TEXT,
    a2_nama          TEXT,
    a2_status        TEXT,
    a3_nama          TEXT,
    a3_status        TEXT,

    -- Konsensus KimFis (majority vote)
    status_kimfis    TEXT,
    remark_analis    TEXT,

    -- Hasil Verifikator
    tgl_verifikasi   TEXT,
    verifikator      TEXT,
    status_verif     TEXT,
    remark_verif     TEXT,

    -- Perbandingan
    comparison       TEXT,
    gap              TEXT,

    -- Metadata
    source_file      TEXT,
    created_at       TEXT DEFAULT (datetime('now')),

    PRIMARY KEY (no_batch, mix_ibc)
);

CREATE INDEX IF NOT EXISTS idx_produk    ON sensory_clean(produk_grade);
CREATE INDEX IF NOT EXISTS idx_tgl       ON sensory_clean(tgl_analisa);
CREATE INDEX IF NOT EXISTS idx_tgl_verif ON sensory_clean(tgl_verifikasi);
CREATE INDEX IF NOT EXISTS idx_comparison ON sensory_clean(comparison);
CREATE INDEX IF NOT EXISTS idx_plant     ON sensory_clean(plant);
"""


def build_clean_table(df):
    """Konversi DataFrame dari load_data ke format tabel flat."""

    def _get_col(dfr, no, suffix):
        for c in [f"A{no}_{suffix}", f"A{int(no)}_{suffix}", f"A{no}.0_{suffix}"]:
            if c in dfr.columns: return c
        return None

    rows = []
    for _, r in df.iterrows():
        rows.append({
            "no_batch":       r.get("Batch_No"),
            "mix_ibc":        r.get("Mix_Code"),
            "tgl_analisa":    str(r["Date"])[:10] if pd.notna(r.get("Date")) else None,
            "produk_grade":   r.get("Product_Name"),
            "shift":          r.get("Shift_Code"),
            "plant":          r.get("Plant"),
            "a1_nama":        str(r.get(_get_col(df,1,"Name") or "","") or "").strip().title() or None,
            "a1_status":      r.get(_get_col(df,1,"Status") or "", None),
            "a2_nama":        str(r.get(_get_col(df,2,"Name") or "","") or "").strip().title() or None,
            "a2_status":      r.get(_get_col(df,2,"Status") or "", None),
            "a3_nama":        str(r.get(_get_col(df,3,"Name") or "","") or "").strip().title() or None,
            "a3_status":      r.get(_get_col(df,3,"Status") or "", None),
            "status_kimfis":  r.get("KF_Status"),
            "remark_analis":  r.get("Remark_Analyst"),
            "tgl_verifikasi": str(r["Verif_Date"])[:10] if pd.notna(r.get("Verif_Date")) else None,
            "verifikator":    str(r.get("Verif_Name","") or "").strip().title() or None,
            "status_verif":   r.get("Verif_Status"),
            "remark_verif":   r.get("Remark_Verif"),
            "comparison":     r.get("Comparison"),
            "gap":            r.get("Gap_Type"),
            "source_file":    r.get("Source_File"),
        })

    # Bersihkan nilai "nan" string
    clean = pd.DataFrame(rows)
    for col in clean.columns:
        clean[col] = clean[col].apply(
            lambda x: None if str(x).strip().lower() in ("nan","none","") else x
        )
    return clean


def insert_to_db(df_clean):
    """Insert DataFrame ke SQLite, replace jika sudah ada."""
    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f"  Database lama dihapus: {DB_PATH.name}")

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()

    inserted = 0
    cur = conn.cursor()
    for _, r in df_clean.iterrows():
        cur.execute("""
            INSERT OR REPLACE INTO sensory_clean (
                no_batch, mix_ibc, tgl_analisa, produk_grade, shift, plant,
                a1_nama, a1_status, a2_nama, a2_status, a3_nama, a3_status,
                status_kimfis, remark_analis,
                tgl_verifikasi, verifikator, status_verif, remark_verif,
                comparison, gap, source_file
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            r["no_batch"], r["mix_ibc"], r["tgl_analisa"], r["produk_grade"],
            r["shift"], r["plant"],
            r["a1_nama"], r["a1_status"], r["a2_nama"], r["a2_status"],
            r["a3_nama"], r["a3_status"],
            r["status_kimfis"], r["remark_analis"],
            r["tgl_verifikasi"], r["verifikator"], r["status_verif"], r["remark_verif"],
            r["comparison"], r["gap"], r["source_file"],
        ))
        inserted += cur.rowcount

    conn.commit()
    conn.close()

    kb = DB_PATH.stat().st_size / 1024
    print(f"  Inserted : {inserted:,} baris")
    print(f"  DB size  : {kb:.0f} KB")
    print(f"  Lokasi   : {DB_PATH}")


def verify(df_clean):
    """Tampilkan ringkasan hasil ETL."""
    total      = len(df_clean)
    terverif   = df_clean["tgl_verifikasi"].notna().sum()
    match      = (df_clean["comparison"] == "MATCH").sum()
    mismatch   = (df_clean["comparison"] == "MISMATCH").sum()
    no_verif   = (df_clean["comparison"] == "NO_VERIFICATION").sum()
    coverage   = terverif / total * 100 if total else 0

    print(f"\n  Total Mix/IBC  : {total:,}")
    print(f"  Terverifikasi  : {terverif:,} ({coverage:.1f}% coverage)")
    print(f"  Match          : {match:,}")
    print(f"  Mismatch       : {mismatch:,}")
    print(f"  No Verification: {no_verif:,}")

    print(f"\n  Top 5 Mismatch Gap:")
    top = df_clean[df_clean["gap"].notna()]["gap"].value_counts().head(5)
    for gap, n in top.items():
        print(f"    {gap:<25} {n:>5}")

    print(f"\n  Produk terbanyak (top 5):")
    top_prod = df_clean["produk_grade"].value_counts().head(5)
    for prod, n in top_prod.items():
        print(f"    {str(prod)[:35]:<37} {n:>5}")


def main():
    print("\n" + "="*55)
    print("  QC SENSORY — ETL to SQLite")
    print("="*55)

    print("\n[1/3] Loading & transforming data dari Excel...")
    df = _load_data(RAW_FOLDER)

    print("\n[2/3] Building clean table...")
    df_clean = build_clean_table(df)
    print(f"  {len(df_clean):,} baris siap dimasukkan ke DB")

    print("\n[3/3] Menyimpan ke SQLite...")
    insert_to_db(df_clean)

    print("\n--- Ringkasan ---")
    verify(df_clean)

    print(f"\n{'='*55}")
    print("  ✅ ETL selesai — qc_sensory.db siap digunakan")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
