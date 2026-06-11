"""
verify_db.py
============
Quality check otomatis untuk database qc_sensory.db setelah ETL selesai.

Cara pakai:
    python database/verify_db.py

Apa yang dicek:
    1. File DB ada dan ukurannya wajar
    2. Jumlah baris di tabel sensory_clean
    3. Rentang tanggal analisa dan verifikasi
    4. Distribusi status KimFis dan Verif (cek typo / nilai aneh)
    5. Distribusi comparison (hanya boleh 3 nilai)
    6. Cek baris tanpa Batch_No atau Mix_IBC (data corrupt)
    7. Top produk dan analis (cek nama tidak jadi NaN)
    8. Sample data terbaru
"""

import sqlite3
from pathlib import Path

_HERE   = Path(__file__).parent
DB_PATH = _HERE / "qc_sensory.db"

VALID_STATUS      = {"TP 2-","TP 1-","Pass","TP 1+","TP 2+","TP 3"}
VALID_COMPARISON  = {"MATCH","MISMATCH","NO_VERIFICATION"}


def _line(char="─", width=55):
    return char * width


def verify():
    print("\n" + _line("="))
    print("  QUALITY CHECK — qc_sensory.db")
    print(_line("="))

    # ── 1. Cek file ada ─────────────────────────────────────────
    if not DB_PATH.exists():
        print("\n❌ File tidak ditemukan:", DB_PATH)
        print("   Jalankan dulu: python database/etl_to_sqlite.py")
        return

    kb = DB_PATH.stat().st_size / 1024
    status_icon = "✅" if kb > 10 else "⚠️"
    print(f"\n{status_icon} File     : {DB_PATH.name}  ({kb:.0f} KB)")

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    issues = []  # kumpulkan semua masalah yang ditemukan

    # ── 2. Jumlah baris ──────────────────────────────────────────
    total = cur.execute("SELECT COUNT(*) FROM sensory_clean").fetchone()[0]
    icon  = "✅" if total > 1000 else "⚠️"
    print(f"{icon} Total    : {total:,} baris (mix/IBC unik)")
    if total == 0:
        issues.append("❌ Tabel sensory_clean kosong — ETL mungkin gagal")
    elif total < 100:
        issues.append(f"⚠️  Jumlah baris sangat sedikit ({total}) — cek file Excel")

    # ── 3. Rentang tanggal ───────────────────────────────────────
    print(f"\n{_line()}")
    print("  📅 Rentang Tanggal")
    print(_line())

    r = cur.execute("""
        SELECT MIN(tgl_analisa), MAX(tgl_analisa),
               MIN(tgl_verifikasi), MAX(tgl_verifikasi)
        FROM sensory_clean
    """).fetchone()

    print(f"  Analisa     : {r[0]} → {r[1]}")
    print(f"  Verifikasi  : {r[2]} → {r[3]}")

    if r[0] is None:
        issues.append("⚠️  Semua tgl_analisa kosong — cek kolom Date di Excel")

    # ── 4. Distribusi status KimFis ──────────────────────────────
    print(f"\n{_line()}")
    print("  ✅ Distribusi Status KimFis")
    print(_line())

    rows = cur.execute("""
        SELECT status_kimfis, COUNT(*) as n
        FROM sensory_clean
        GROUP BY status_kimfis
        ORDER BY n DESC
    """).fetchall()

    total_status = sum(r[1] for r in rows)
    for status, n in rows:
        pct  = n / total_status * 100 if total_status else 0
        icon = "✅" if status in VALID_STATUS else "❌"
        tag  = "" if status in VALID_STATUS else "  ← NILAI TIDAK VALID!"
        print(f"  {icon} {str(status):<12} {n:>6,}  ({pct:.1f}%){tag}")
        if status not in VALID_STATUS:
            issues.append(f"❌ Status KimFis tidak valid: '{status}'")

    # ── 5. Distribusi status Verif ───────────────────────────────
    print(f"\n{_line()}")
    print("  ✅ Distribusi Status Verif")
    print(_line())

    rows = cur.execute("""
        SELECT status_verif, COUNT(*) as n
        FROM sensory_clean
        WHERE status_verif IS NOT NULL
        GROUP BY status_verif
        ORDER BY n DESC
    """).fetchall()

    for status, n in rows:
        icon = "✅" if status in VALID_STATUS else "❌"
        tag  = "" if status in VALID_STATUS else "  ← NILAI TIDAK VALID!"
        print(f"  {icon} {str(status):<12} {n:>6,}{tag}")
        if status not in VALID_STATUS:
            issues.append(f"❌ Status Verif tidak valid: '{status}'")

    # ── 6. Distribusi Comparison ─────────────────────────────────
    print(f"\n{_line()}")
    print("  📈 Distribusi Comparison")
    print(_line())

    rows = cur.execute("""
        SELECT comparison, COUNT(*) as n
        FROM sensory_clean
        GROUP BY comparison
        ORDER BY n DESC
    """).fetchall()

    total_comp = sum(r[1] for r in rows)
    for comp, n in rows:
        pct  = n / total_comp * 100 if total_comp else 0
        icon = "✅" if comp in VALID_COMPARISON else "❌"
        tag  = "" if comp in VALID_COMPARISON else "  ← NILAI TIDAK VALID!"
        print(f"  {icon} {str(comp):<22} {n:>6,}  ({pct:.1f}%){tag}")
        if comp not in VALID_COMPARISON:
            issues.append(f"❌ Comparison tidak valid: '{comp}'")

    # ── 7. Cek data corrupt ──────────────────────────────────────
    print(f"\n{_line()}")
    print("  🔍 Cek Data Integrity")
    print(_line())

    # Baris tanpa PK
    n_null_pk = cur.execute("""
        SELECT COUNT(*) FROM sensory_clean
        WHERE no_batch IS NULL OR mix_ibc IS NULL
    """).fetchone()[0]
    icon = "✅" if n_null_pk == 0 else "❌"
    print(f"  {icon} Baris tanpa no_batch/mix_ibc  : {n_null_pk}")
    if n_null_pk > 0:
        issues.append(f"❌ Ada {n_null_pk} baris tanpa Primary Key")
        detail = cur.execute("""
            SELECT no_batch, mix_ibc, produk_grade, tgl_analisa
            FROM sensory_clean
            WHERE no_batch IS NULL OR mix_ibc IS NULL
            LIMIT 10
        """).fetchall()
        print(f"       Detail (maks 10):")
        for d in detail:
            print(f"       → Batch={d[0]} Mix={d[1]} | {d[2]} | {d[3]}")

    # Baris dengan nama analis = "Nan" / kosong
    n_nan_analyst = cur.execute("""
        SELECT COUNT(*) FROM sensory_clean
        WHERE lower(a1_nama) IN ('nan','none','')
           OR a1_nama IS NULL
    """).fetchone()[0]
    icon = "✅" if n_nan_analyst == 0 else "⚠️"
    print(f"  {icon} Baris tanpa nama analis A1     : {n_nan_analyst}")
    if n_nan_analyst > 0:
        detail = cur.execute("""
            SELECT no_batch, mix_ibc, produk_grade, tgl_analisa,
                   a1_status, source_file
            FROM sensory_clean
            WHERE lower(a1_nama) IN ('nan','none','')
               OR a1_nama IS NULL
            ORDER BY tgl_analisa
        """).fetchall()
        print(f"       Detail batch yang perlu dicek di file Excel:")
        for d in detail:
            print(f"       → Batch {d[0]} Mix {d[1]}"
                  f" | {str(d[2])[:25]:<25}"
                  f" | {d[3]}"
                  f" | A1_status={d[4]}"
                  f" | file: {d[5]}")
        if n_nan_analyst > 100:
            issues.append(f"⚠️  Banyak baris tanpa nama analis ({n_nan_analyst})")

    # Duplikat PK
    n_dup = cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT no_batch, mix_ibc, COUNT(*) as c
            FROM sensory_clean
            GROUP BY no_batch, mix_ibc
            HAVING c > 1
        )
    """).fetchone()[0]
    icon = "✅" if n_dup == 0 else "❌"
    print(f"  {icon} Duplikat (no_batch + mix_ibc)  : {n_dup}")
    if n_dup > 0:
        issues.append(f"❌ Ada {n_dup} duplikat Primary Key")
        detail = cur.execute("""
            SELECT no_batch, mix_ibc, COUNT(*) as c
            FROM sensory_clean
            GROUP BY no_batch, mix_ibc
            HAVING c > 1
            ORDER BY c DESC
            LIMIT 10
        """).fetchall()
        print(f"       Detail (maks 10):")
        for d in detail:
            print(f"       → Batch {d[0]} Mix {d[1]} muncul {d[2]}x")

    # Status tidak valid — tampilkan batch yang bermasalah
    invalid_kf = cur.execute("""
        SELECT no_batch, mix_ibc, produk_grade, status_kimfis,
               tgl_analisa, source_file
        FROM sensory_clean
        WHERE status_kimfis NOT IN
              ('TP 2-','TP 1-','Pass','TP 1+','TP 2+','TP 3')
          AND status_kimfis IS NOT NULL
        LIMIT 10
    """).fetchall()
    if invalid_kf:
        print(f"\n  ❌ Batch dengan Status KimFis tidak valid:")
        for d in invalid_kf:
            print(f"       → Batch {d[0]} Mix {d[1]}"
                  f" | {str(d[2])[:20]:<20}"
                  f" | status='{d[3]}'"
                  f" | {d[4]} | {d[5]}")

    invalid_vf = cur.execute("""
        SELECT no_batch, mix_ibc, produk_grade, status_verif,
               tgl_verifikasi, source_file
        FROM sensory_clean
        WHERE status_verif NOT IN
              ('TP 2-','TP 1-','Pass','TP 1+','TP 2+','TP 3')
          AND status_verif IS NOT NULL
        LIMIT 10
    """).fetchall()
    if invalid_vf:
        print(f"\n  ❌ Batch dengan Status Verif tidak valid:")
        for d in invalid_vf:
            print(f"       → Batch {d[0]} Mix {d[1]}"
                  f" | {str(d[2])[:20]:<20}"
                  f" | status='{d[3]}'"
                  f" | {d[4]} | {d[5]}")

    # ── 8. Top produk ────────────────────────────────────────────
    print(f"\n{_line()}")
    print("  🏭 Top 5 Produk")
    print(_line())

    rows = cur.execute("""
        SELECT produk_grade, COUNT(*) as n
        FROM sensory_clean
        WHERE produk_grade IS NOT NULL
        GROUP BY produk_grade
        ORDER BY n DESC LIMIT 5
    """).fetchall()

    for prod, n in rows:
        short = str(prod)[:40] + "…" if len(str(prod)) > 40 else str(prod)
        icon  = "⚠️" if str(prod).lower() in ("nan","none","") else "  "
        print(f"  {icon} {short:<42} {n:>5,}")

    # ── 9. Top analis ────────────────────────────────────────────
    print(f"\n{_line()}")
    print("  👤 Top 5 Analis KimFis")
    print(_line())

    rows = cur.execute("""
        SELECT a1_nama, COUNT(*) as n
        FROM sensory_clean
        WHERE a1_nama IS NOT NULL
          AND lower(a1_nama) NOT IN ('nan','none','')
        GROUP BY a1_nama
        ORDER BY n DESC LIMIT 5
    """).fetchall()

    for name, n in rows:
        print(f"    {str(name).title():<25} {n:>5,} batch sebagai A1")

    # ── 10. Sample data terbaru ──────────────────────────────────
    print(f"\n{_line()}")
    print("  📋 3 Data Terbaru (by tgl_verifikasi)")
    print(_line())

    rows = cur.execute("""
        SELECT tgl_verifikasi, produk_grade, no_batch, mix_ibc,
               status_kimfis, status_verif, comparison
        FROM sensory_clean
        WHERE tgl_verifikasi IS NOT NULL
        ORDER BY tgl_verifikasi DESC
        LIMIT 3
    """).fetchall()

    for r in rows:
        print(f"  {r[0]} | {str(r[1])[:20]:<20} | Batch {r[2]} Mix {r[3]}")
        print(f"           KF={r[4]} Verif={r[5]} → {r[6]}")

    conn.close()

    # ── Ringkasan akhir ──────────────────────────────────────────
    print(f"\n{_line('=')}")
    if issues:
        print(f"  ⚠️  DITEMUKAN {len(issues)} MASALAH:")
        for isu in issues:
            print(f"     {isu}")
    else:
        print("  ✅ SEMUA CHECK PASSED — Database siap digunakan")
    print(_line("=") + "\n")


if __name__ == "__main__":
    verify()
