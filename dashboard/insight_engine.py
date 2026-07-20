"""
insight_engine.py
=================
Fungsi auto-generate insight & recommendation untuk Tab 2, 3, 4.
Prinsip:
  1. Threshold relatif (max/mean+std) — bukan absolut
  2. Selalu sertakan n=
  3. Guard small sample (< 20)
  4. Hindari kausalitas — hanya catat korelasi/pola
  5. Layer 1 (observable) selalu tampil
  6. Layer 2 (inference) hanya kalau kondisi terpenuhi (dominansi > 60%)
  7. Layer 3 (hypothesis) statis + disclaimer eksplisit
"""

import pandas as pd
import numpy as np
import math


MIN_N = 20  # minimum sampel untuk insight reliable

CONFOUNDING_NOTE = (
    "Perbandingan ini belum memperhitungkan bahwa tiap kelompok bisa memproses "
    "produk yang berbeda-beda, jadi selisihnya belum tentu murni disebabkan oleh "
    "faktor ini sendiri."
)


def _ztest_pvalue(p1: float, n1: int, p2: float, n2: int):
    """
    Two-proportion z-test. p1/p2 dalam desimal (0-1), n1/n2 jumlah sampel.
    Return p-value, atau None kalau salah satu n=0.
    """
    if n1 == 0 or n2 == 0:
        return None
    pooled = (p1 * n1 + p2 * n2) / (n1 + n2)
    if pooled <= 0 or pooled >= 1:
        return 1.0
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se == 0:
        return 1.0
    z = (p1 - p2) / se
    return 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))


def _gammaq(s: float, x: float):
    """
    Regularized upper incomplete gamma Q(s,x) — dipakai buat hitung p-value
    chi-square tanpa scipy. Implementasi standar (series + continued fraction).
    """
    if x < 0 or s <= 0:
        return None
    if x == 0:
        return 1.0
    if x < s + 1:
        # Series expansion — valid buat x < s+1
        term = 1.0 / s
        total = term
        n = s
        for _ in range(300):
            n += 1
            term *= x / n
            total += term
            if abs(term) < abs(total) * 1e-14:
                break
        return 1.0 - total * math.exp(-x + s * math.log(x) - math.lgamma(s))
    else:
        # Continued fraction — valid buat x >= s+1
        tiny = 1e-300
        b = x + 1 - s
        c = 1 / tiny
        d = 1 / b
        h = d
        for i in range(1, 300):
            an = -i * (i - s)
            b += 2
            d = an * d + b
            if abs(d) < tiny:
                d = tiny
            c = b + an / c
            if abs(c) < tiny:
                c = tiny
            d = 1 / d
            delta = d * c
            h *= delta
            if abs(delta - 1) < 1e-14:
                break
        return math.exp(-x + s * math.log(x) - math.lgamma(s)) * h


def _chi2_pvalue(chi2_stat: float, dof: int):
    """P-value dari statistik chi-square dengan derajat kebebasan dof."""
    if chi2_stat < 0 or dof <= 0:
        return None
    return _gammaq(dof / 2.0, chi2_stat / 2.0)


def _chi2_contingency(table: list) -> dict:
    """
    Chi-square test of independence — cek apakah 2 variabel kategori
    (misal: jenis gap x shift) SALING BERHUBUNGAN, atau independen
    (polanya sama aja di semua kelompok).

    table: list of list, baris = grup (misal shift), kolom = kategori
    (misal jenis gap). Beda dari _chi2_omnibus yang khusus 2 kolom
    (event/non-event) — ini general buat berapapun jumlah kolom.

    Return dict: chi2, dof, p_value, valid (False kalau ada expected
    frequency < 5 di terlalu banyak sel — chi-square jadi kurang akurat).
    """
    import numpy as np
    arr = np.array(table, dtype=float)
    if arr.shape[0] < 2 or arr.shape[1] < 2:
        return {"chi2": None, "dof": None, "p_value": None, "valid": False}

    row_sums = arr.sum(axis=1, keepdims=True)
    col_sums = arr.sum(axis=0, keepdims=True)
    total = arr.sum()
    if total == 0:
        return {"chi2": None, "dof": None, "p_value": None, "valid": False}

    expected = row_sums @ col_sums / total
    # Guard: chi-square kurang valid kalau banyak sel expected-nya < 5
    # (aturan baku Cochran) — daripada hasil menyesatkan, tandai invalid.
    low_cells = (expected < 5).sum()
    valid = low_cells <= 0.2 * expected.size  # toleransi maks 20% sel

    with np.errstate(divide="ignore", invalid="ignore"):
        chi2_stat = np.where(expected > 0, (arr - expected) ** 2 / expected, 0).sum()
    dof = (arr.shape[0] - 1) * (arr.shape[1] - 1)
    p_value = _chi2_pvalue(chi2_stat, dof)

    return {"chi2": round(chi2_stat, 2), "dof": dof, "p_value": p_value, "valid": valid}


def _chi2_omnibus(groups: list) -> dict:
    """
    Chi-square test of homogeneity — cek apakah ADA beda di antara SEMUA
    grup sekaligus (omnibus test), SEBELUM drill-down cari pasangan
    ekstrem. Ini yang mencegah "nyari-nyari pasangan paling beda dari
    banyak grup, baru dites" (multiple comparison problem).

    groups: list of (n_event, n_total) — misal [(gap, total), ...] per shift.
    Return dict: chi2, dof, p_value.
    """
    k = len(groups)
    if k < 2:
        return {"chi2": None, "dof": None, "p_value": None}

    total_event = sum(g[0] for g in groups)
    total_n     = sum(g[1] for g in groups)
    if total_n == 0:
        return {"chi2": None, "dof": None, "p_value": None}
    overall_rate = total_event / total_n

    chi2_stat = 0.0
    for n_event, n_total in groups:
        if n_total == 0:
            continue
        for observed, expected in [
            (n_event, n_total * overall_rate),
            (n_total - n_event, n_total * (1 - overall_rate)),
        ]:
            if expected > 0:
                chi2_stat += (observed - expected) ** 2 / expected

    dof = k - 1
    p_value = _chi2_pvalue(chi2_stat, dof)
    return {"chi2": round(chi2_stat, 2), "dof": dof, "p_value": p_value}


def _severity(status: str) -> int:
    """
    Jarak dari Pass — makin kecil makin baik (lebih dekat standar).
    TP 3 selalu dianggap paling parah (terlepas dari skala -2..2).
    """
    SEV_MAP = {"Pass": 0, "TP 1-": 1, "TP 1+": 1, "TP 2-": 2, "TP 2+": 2, "TP 3": 99}
    return SEV_MAP.get(status, 0)


# ══════════════════════════════════════════════════════════════════
# TAB 2 — Gap Type Insight
# ══════════════════════════════════════════════════════════════════

def gen_insight_gap_type(df_mm: pd.DataFrame, total_mm: int) -> dict:
    """
    Generate insight dari distribusi tipe gap.
    Returns dict: status, observable, inference, action, confirm
    """
    if total_mm < MIN_N:
        return {
            "status": "insufficient",
            "msg": f"⚠️ Data terlalu sedikit untuk insight yang reliable (n={total_mm}, minimum {MIN_N})."
        }

    # Layer 1: observable
    from tabs.tab2_gap import classify_gap
    df_mm = df_mm.copy()
    df_mm["Kategori"] = df_mm.apply(
        lambda r: classify_gap(r["KF_Status"], r["Verif_Status"]), axis=1
    )
    counts = df_mm["Kategori"].value_counts()
    top_cat   = counts.index[0] if not counts.empty else None
    top_n     = int(counts.iloc[0]) if not counts.empty else 0
    top_pct   = round(top_n / total_mm * 100, 1)
    tp3_n     = int(counts.get("Melibatkan TP 3", 0))
    tp3_pct   = round(tp3_n / total_mm * 100, 1)
    beda_arah_n   = int(counts.get("Beda Arah", 0))
    beda_arah_pct = round(beda_arah_n / total_mm * 100, 1)

    observable = (
        f"Dari {total_mm:,} gap — "
        f"**{top_cat}** mendominasi dengan **{top_n:,} kejadian ({top_pct}%)**."
        + (f" TP 3 terlibat dalam {tp3_n} gap ({tp3_pct}%)." if tp3_n > 0 else "")
    )

    # Layer 2: inference — hanya kalau dominan > 60%
    inference = None
    if top_pct >= 60:
        if top_cat == "Beda Tingkatan":
            inference = (
                f"{top_pct}% gap adalah **Beda Tingkatan** — "
                f"arah penilaian sama (kurang/lebih), cuma beda 1 level, dan "
                f"TIDAK melibatkan TP 2 (murni Pass↔TP1). Ini pola paling ringan, "
                f"masih dalam batas wajar kalibrasi."
            )
        elif top_cat == "Gap Signifikan":
            inference = (
                f"{top_pct}% gap adalah **Gap Signifikan** — melibatkan TP 2 "
                f"(baik lompat dari Pass, atau cuma dari TP 1 ke TP 2). TP 2 "
                f"adalah titik di mana business rule mewajibkan Triangle Test, "
                f"jadi gap di sini lebih genting dibanding Beda Tingkatan "
                f"walau kadang cuma beda 1 level secara angka."
            )
        elif top_cat == "Beda Arah":
            inference = (
                f"{top_pct}% gap adalah **Beda Arah** — "
                f"KimFis dan Verifikator beda persepsi dasar: "
                f"satu menilai produk kurang, satu menilai lebih. "
                f"Ini lebih jarang terjadi tapi perlu penanganan khusus."
            )
        elif top_cat == "Melibatkan TP 3":
            inference = (
                f"Dengan {top_pct}% melibatkan TP 3 (off-taste), ini adalah "
                f"proporsi yang perlu perhatian segera — "
                f"gap di level off-taste berisiko tinggi terhadap kualitas produk."
            )
    else:
        inference = (
            f"Gap terdistribusi merata antar tipe — tidak ada satu tipe yang "
            f"sangat dominan (tertinggi {top_pct}%). "
            f"Perlu investigasi per tipe secara terpisah."
        )

    # Layer 3: action — selalu ada, berbasis top_cat
    action_map = {
        "Beda Tingkatan": (
            "Prioritaskan **screening (training) bertingkat** untuk kalibrasi sensorik analis — sesi deteksi intensitas per parameter (Creamy bertingkat, Milky bertingkat, dst.)."
        ),
        "Gap Signifikan": (
            "**Tinjau ulang kalibrasi di sekitar batas TP 2** — karena gap di sini "
            "berarti salah satu pihak (KimFis atau Verifikator) berada di ambang "
            "keputusan Triangle Test sementara pihak lain menilai jauh lebih ringan. "
            "Cek batch spesifik di Tab Daily Report sebelum ambil keputusan blok."
        ),
        "Beda Arah": (
            "Lakukan **screening (training) persepsi dasar** — "
            "sesi kalibrasi khusus untuk menyamakan pemahaman "
            "arah kurang (-) vs lebih (+) per parameter, "
            "bersama seluruh analis dan Verifikator."
        ),
        "Melibatkan TP 3": (
            "**Eskalasi ke QC Manager** — identifikasi batch spesifik yang "
            "melibatkan TP 3 di Tab Daily Report. Lakukan Triangle Test "
            "untuk justifikasi sebelum keputusan blok."
        ),
    }
    action = action_map.get(top_cat, "Tinjau distribusi tipe gap dan diskusikan dengan tim QC.")

    # Konfirmasi yang dibutuhkan
    confirm = (
        "Analisis ini hanya mencakup data sensory — temuan di atas adalah batas lingkup yang bisa kami olah dari data evaluasi sensory."
    )

    return {
        "status":     "ok",
        "observable": observable,
        "inference":  inference,
        "action":     action,
        "confirm":    confirm,
        "tp3_alert":  tp3_n > 0 and tp3_pct >= 5,
    }


def gen_insight_gap_type_by_dim(df_mm: pd.DataFrame, dim_col: str, dim_label: str) -> dict:
    """
    Chi-square test of independence — apakah JENIS gap (Beda Tingkatan/Beda
    Arah/Gap Signifikan/Melibatkan TP 3) polanya beda-beda tergantung dimensi
    tertentu (shift/analis/dll), atau independen (pola sebarannya sama rata
    di semua dimensi).

    Beda dari gen_insight_shift/gen_insight_quality_by_dim (yang nanya
    "apakah RATE-nya beda"), ini nanya "apakah CORAK/TIPE gap-nya beda".

    df_mm: DataFrame baris MISMATCH — harus punya kolom KF_Status,
    Verif_Status, dan dim_col (misal 'Shift_Label').
    dim_label: nama dimensi untuk teks, misal "shift".
    """
    from tabs.tab2_gap import classify_gap

    df_mm = df_mm.copy()
    df_mm["Kategori"] = df_mm.apply(
        lambda r: classify_gap(r["KF_Status"], r["Verif_Status"]), axis=1
    )

    # Coba dulu pakai 4 kategori penuh; kalau selnya terlalu tipis
    # (expected < 5 di >20% sel), turun ke versi 2-kategori yang lebih kasar
    # tapi valid secara statistik.
    table_full = pd.crosstab(df_mm[dim_col], df_mm["Kategori"])
    table_full = table_full.loc[table_full.sum(axis=1) >= MIN_N]

    result, used_simplified, table_used = {"valid": False}, False, table_full
    if table_full.shape[0] >= 2 and table_full.shape[1] >= 2:
        result = _chi2_contingency(table_full.values.tolist())

    if not result.get("valid", False):
        df_mm["Kategori2"] = df_mm["Kategori"].apply(
            lambda k: "Beda Tingkatan" if k == "Beda Tingkatan" else "Perlu Perhatian"
        )
        table2 = pd.crosstab(df_mm[dim_col], df_mm["Kategori2"])
        table2 = table2.loc[table2.sum(axis=1) >= MIN_N]
        if table2.shape[0] < 2 or table2.shape[1] < 2:
            return {"status": "insufficient",
                    "msg": f"Data terlalu sedikit untuk uji pola jenis gap per {dim_label}."}
        result = _chi2_contingency(table2.values.tolist())
        used_simplified, table_used = True, table2

    if not result.get("valid", False) or result.get("p_value") is None:
        return {"status": "insufficient",
                "msg": f"Data terlalu tersebar untuk uji chi-square yang valid per {dim_label} "
                       f"(banyak sel dengan sampel < 5)."}

    p_value = result["p_value"]
    kategori_note = (
        "disederhanakan jadi 2 kategori — Beda Tingkatan vs Perlu Perhatian — "
        "karena kategori aslinya terlalu tipis untuk diuji langsung"
        if used_simplified else "4 kategori penuh"
    )

    observable = (
        f"Diuji pola jenis gap ({kategori_note}) di {table_used.shape[0]} {dim_label} sekaligus."
    )

    if p_value >= 0.05:
        inference = (
            f"Belum cukup bukti pola jenis gap berhubungan dengan {dim_label} — proporsi "
            f"tiap jenis gap relatif konsisten di semua {dim_label}, bukan terkonsentrasi "
            f"di salah satu {dim_label} tertentu."
        )
        action = (
            f"Tidak ada indikasi {dim_label} tertentu punya corak gap yang beda — "
            f"penanganan gap tidak perlu dibedakan per {dim_label}."
        )
    else:
        inference = (
            f"Ada hubungan nyata antara jenis gap dan {dim_label} — proporsi jenis gap "
            f"TIDAK merata, ada {dim_label} tertentu yang corak gap-nya beda dari yang lain."
        )
        action = (
            f"Cek tabel detail untuk lihat {dim_label} mana yang polanya paling menonjol, "
            f"dan jenis gap apa yang lebih sering muncul di situ — itu petunjuk awal, "
            f"perlu ditelusuri lebih lanjut sebelum disimpulkan penyebabnya."
        )

    return {
        "status": "ok",
        "observable": observable,
        "inference": inference,
        "action": action,
        "confirm": (
            "Analisis ini hanya mencakup data sensory — temuan di atas adalah batas lingkup "
            "yang bisa kami olah dari data evaluasi sensory. " + CONFOUNDING_NOTE
        ),
    }


def gen_insight_trend(monthly: pd.DataFrame) -> dict:
    """
    Generate insight dari trend bulanan gap rate.
    monthly: DataFrame dengan kolom Month, Gap Rate %, Mismatch, Total
    """
    if len(monthly) < 2:
        return {"status": "insufficient", "msg": "Perlu minimal 2 bulan data untuk analisis trend."}

    worst = monthly.loc[monthly["Gap Rate %"].idxmax()]
    best  = monthly.loc[monthly["Gap Rate %"].idxmin()]
    mean_rate = monthly["Gap Rate %"].mean()
    std_rate  = monthly["Gap Rate %"].std()
    last_rate = monthly.iloc[-1]["Gap Rate %"]
    prev_rate = monthly.iloc[-2]["Gap Rate %"] if len(monthly) >= 2 else None

    # Trend: apakah bulan terakhir di atas atau bawah rata-rata?
    trend_direction = None
    if prev_rate is not None:
        if last_rate > prev_rate + 2:
            trend_direction = "memburuk"
        elif last_rate < prev_rate - 2:
            trend_direction = "membaik"
        else:
            trend_direction = "stabil"

    observable = (
        f"Gap rate tertinggi: **{worst['Month']}** ({worst['Gap Rate %']}%, "
        f"{int(worst['Mismatch'])} gap dari {int(worst['Total'])} sampel). "
        f"Terendah: **{best['Month']}** ({best['Gap Rate %']}%). "
        f"Rata-rata: {mean_rate:.1f}%."
    )

    # Layer 2: inference berdasarkan variabilitas (tanpa tampilkan std ke user)
    cv = std_rate / mean_rate if mean_rate > 0 else 0  # coefficient of variation
    if cv > 0.2:
        inference = (
            f"Gap rate berfluktuasi cukup besar antar bulan — "
            f"ada faktor situasional yang perlu ditelusuri "
            f"(misalnya rotasi analis, jenis produk yang diproduksi, atau kondisi tertentu)."
        )
    else:
        inference = (
            f"Gap rate cenderung stabil dari bulan ke bulan — "
            f"ini pola yang konsisten, bukan kejadian sesekali. "
            f"Perlu perbaikan menyeluruh, bukan hanya penanganan per kejadian."
        )

    action = None
    if trend_direction == "memburuk":
        bridge = (
            "Meski pola keseluruhan tergolong stabil, " if cv <= 0.2 else ""
        )
        action = (
            f"{bridge}Bulan terakhir ({monthly.iloc[-1]['Month']}) gap rate {last_rate}% — "
            f"**lebih tinggi dari bulan sebelumnya** ({prev_rate}%). "
            f"Perlu dipantau apakah ini awal tren naik atau sekadar variasi bulanan biasa: "
            f"cek perubahan komposisi analis, produk, atau proses di bulan ini."
        )
    elif trend_direction == "membaik":
        bridge = (
            "Melanjutkan pola keseluruhan yang sudah stabil, " if cv <= 0.2 else ""
        )
        action = (
            f"{bridge}Bulan terakhir ({monthly.iloc[-1]['Month']}) gap rate {last_rate}% — "
            f"**membaik dari bulan sebelumnya** ({prev_rate}%). "
            f"Identifikasi apa yang berubah dan pertahankan kondisi tersebut."
        )
    else:
        action = (
            f"Gap rate stabil di sekitar {mean_rate:.1f}%. "
            f"Target: turunkan secara bertahap lewat sesi kalibrasi rutin."
        )

    return {
        "status":      "ok",
        "observable":  observable,
        "inference":   inference,
        "action":      action,
        "worst_month": worst["Month"],
        "best_month":  best["Month"],
    }


# ══════════════════════════════════════════════════════════════════
# TAB 3 — Parameter & Produk Insight
# ══════════════════════════════════════════════════════════════════

def gen_insight_parameter(param_stats: list[dict]) -> dict:
    """
    Generate insight dari list stat per parameter.
    param_stats: list of {param, total, mismatch, rate, tp_rate, direction}
    direction: "kurang" / "lebih" / "mixed" / None
    """
    valid = [p for p in param_stats if p.get("total", 0) >= MIN_N]
    if not valid:
        return {"status": "insufficient", "msg": f"Data terlalu sedikit (minimum n={MIN_N} per parameter)."}

    # Urutkan by gap rate descending
    ranked = sorted(valid, key=lambda x: x["rate"], reverse=True)
    top    = ranked[0]
    bottom = ranked[-1]

    # Threshold relatif
    rates     = [p["rate"] for p in valid]
    mean_rate = np.mean(rates)
    std_rate  = np.std(rates)
    # Parameter "kritis" = rate > mean + 0.5*std
    critical  = [p for p in valid if p["rate"] > mean_rate + 0.5 * std_rate]

    observable = (
        f"Parameter dengan gap rate tertinggi: **{top['param']}** "
        f"({top['rate']}% dari {top['total']:,} sampel). "
        + (f"**{bottom['param']}** paling rendah ({bottom['rate']}%)." if len(ranked) > 1 else "")
        + (f" {len(critical)} parameter dengan gap rate menonjol dibanding yang lain."
           if len(critical) > 0 else "")
    )

    # Layer 2: inference dari arah dominan parameter teratas
    direction = top.get("direction")
    inference = None
    if direction == "kurang":
        inference = (
            f"Gap {top['param']} kebanyakan arah **kurang (↓)** — "
            f"analis menilai sudah Pass, Verifikator menilai masih kurang. "
            f"Analis dan Verifikator perlu menyamakan persepsi "
            f"soal standar {top['param']}."
        )
    elif direction == "lebih":
        inference = (
            f"Gap {top['param']} kebanyakan arah **lebih (↑)** — "
            f"analis menilai berlebih, Verifikator menilai masih dalam batas. "
            f"Perlu samakan persepsi soal batas atas {top['param']}."
        )
    elif direction == "mixed":
        inference = (
            f"Gap {top['param']} tidak punya arah yang konsisten — "
            f"analis dan Verifikator beda arah secara bergantian. "
            f"Standar referensi {top['param']} perlu diperjelas bersama."
        )

    crit_names = ", ".join([p["param"] for p in critical[:3]])
    action = (
        f"Fokuskan **screening bertingkat** berikutnya ke parameter "
        f"**{crit_names}** — latih analis membedakan tingkatan "
        f"Pass, TP 1, dan TP 2 untuk parameter ini."
    ) if critical else (
        "Gap rate semua parameter relatif merata — "
        "lakukan screening bertingkat untuk seluruh parameter secara bersama."
    )

    confirm = (
        "Analisis ini hanya mencakup data sensory — temuan di atas adalah "
        "batas lingkup yang bisa kami olah dari data evaluasi sensory."
    )

    return {
        "status":     "ok",
        "observable": observable,
        "inference":  inference,
        "action":     action,
        "confirm":    confirm,
        "top_param":  top["param"],
        "critical":   [p["param"] for p in critical],
    }


def gen_insight_product(prod_name: str, tp_rate: float, pass_rate: float,
                         n_total: int, top_param: str, top_direction: str) -> dict:
    """
    Generate insight untuk drill-down 1 produk.
    """
    if n_total < MIN_N:
        return {
            "status": "insufficient",
            "msg": f"⚠️ Data terlalu sedikit untuk {prod_name} (n={n_total}, minimum {MIN_N})."
        }

    # Layer 1
    observable = (
        f"**{prod_name}**: {n_total:,} sampel · "
        f"Pass rate {pass_rate:.1f}% · TP rate {tp_rate:.1f}%."
    )

    # Layer 2
    inference = None
    if tp_rate >= 80:
        inference = (
            f"TP rate {tp_rate:.1f}% sangat tinggi — hampir semua sampel "
            f"tidak mencapai Pass. Ini pola yang konsisten, bukan variasi sesekali."
        )
    elif tp_rate >= 50:
        inference = (
            f"TP rate {tp_rate:.1f}% — lebih dari separuh sampel tidak Pass. "
            f"Produk ini konsisten memerlukan perhatian lebih."
        )
    elif pass_rate >= 80:
        inference = (
            f"Pass rate {pass_rate:.1f}% — produk ini relatif konsisten memenuhi standar."
        )

    # Action — konteks produk (bukan kalibrasi analis)
    if tp_rate >= 50 and top_param:
        action = (
            f"Produk ini konsisten banyak TP di parameter **{top_param}** — "
            f"ini sinyal kualitas produk (bukan masalah kalibrasi analis), layak "
            f"diserahkan ke Produksi/R&D sebagai bukti untuk investigasi lebih lanjut."
        )
    elif top_param:
        action = (
            f"Parameter **{top_param}** paling sering TP di produk ini — "
            f"pantau tren ke depan apakah membaik atau memburuk."
        )
    else:
        action = "Pantau tren pass rate produk ini di bulan-bulan berikutnya."

    return {
        "status":     "ok",
        "observable": observable,
        "inference":  inference,
        "action":     action,
    }


# ══════════════════════════════════════════════════════════════════
# TAB 4 — Shift & Analis Insight
# ══════════════════════════════════════════════════════════════════

def gen_insight_quality_by_dim(q_df: pd.DataFrame, dim_label: str) -> dict:
    """
    Generate insight dari PASS RATE (ground truth Verifikator) per dimensi
    (shift / analis / plant / dll) — lensa OUTCOME, beda dari gen_insight_shift
    yang lensa PROSES (gap KimFis vs Verifikator). Insight ini SENGAJA dipisah
    dari insight gap — jangan digabung jadi satu narasi.
    q_df: kolom [Label, "Pass Rate %", "Pass", "Total"]
    dim_label: nama dimensi untuk teks, misal "shift", "analis"

    Sama seperti gen_insight_shift — omnibus test dulu (semua grup sekaligus),
    baru drill-down ke pasangan ekstrem kalau omnibus-nya signifikan.
    """
    valid = q_df[q_df["Total"] >= MIN_N]
    if valid.empty:
        return {"status": "insufficient", "msg": f"Data {dim_label} terlalu sedikit (minimum n={MIN_N})."}

    worst  = valid.loc[valid["Pass Rate %"].idxmin()]
    best   = valid.loc[valid["Pass Rate %"].idxmax()]
    mean_r = valid["Pass Rate %"].mean()

    observable = (
        f"{dim_label.capitalize()} **{worst['Label']}** pass rate terendah: "
        f"**{worst['Pass Rate %']}%** ({int(worst['Pass'])} Pass dari {int(worst['Total'])} sampel terverifikasi). "
        f"{dim_label.capitalize()} **{best['Label']}** tertinggi: {best['Pass Rate %']}%. "
        f"Rata-rata antar {dim_label}: {mean_r:.1f}%."
    )

    groups = [(int(r["Pass"]), int(r["Total"])) for _, r in valid.iterrows()]
    omnibus = _chi2_omnibus(groups)
    k = len(groups)
    n_pairs = k * (k - 1) // 2
    spread = best["Pass Rate %"] - worst["Pass Rate %"]

    if omnibus["p_value"] is None or omnibus["p_value"] >= 0.05:
        inference = (
            f"Diuji ke SEMUA {k} {dim_label} sekaligus (bukan cuma yang kelihatan "
            f"paling beda) — belum cukup bukti ada perbedaan nyata. Selisih pass rate "
            f"(**{spread:.1f}%**) kemungkinan besar variasi wajar antar {dim_label}."
        )
        action = (
            f"Pass rate antar {dim_label} tidak berbeda signifikan secara keseluruhan — "
            f"belum perlu ditelusuri sebagai masalah spesifik per {dim_label}."
        )
    else:
        alpha_corrected = 0.05 / n_pairs if n_pairs > 0 else 0.05
        pval = _ztest_pvalue(worst["Pass Rate %"] / 100, worst["Total"],
                              best["Pass Rate %"] / 100, best["Total"])
        if pval is not None and pval < alpha_corrected:
            inference = (
                f"Diuji ke semua {k} {dim_label} sekaligus — ADA perbedaan nyata. "
                f"{dim_label.capitalize()} {worst['Label']} vs {best['Label']} adalah "
                f"pasangan paling mencolok (selisih {spread:.1f}%), dan ini tetap "
                f"konsisten meski sudah mempertimbangkan banyaknya pasangan yang "
                f"dibandingkan. Ini soal kualitas hasil sensory-nya sendiri, jadi "
                f"datanya layak diserahkan ke Produksi/R&D."
            )
        else:
            inference = (
                f"Diuji ke semua {k} {dim_label} sekaligus — ADA perbedaan nyata di "
                f"antaranya, tapi pasangan {worst['Label']} vs {best['Label']} secara "
                f"spesifik belum cukup kuat untuk disebut yang paling beda."
            )
        action = (
            f"Kalau pola ini konsisten dari bulan ke bulan, data per {dim_label} ini "
            f"layak diserahkan ke Produksi/R&D sebagai bukti kuantitatif — analisis "
            f"akar penyebab di luar data sensory berada di luar cakupan QC Verifikator."
        )

    return {
        "status": "ok", "observable": observable,
        "inference": inference, "action": action,
        "confirm": (
            "Analisis ini hanya mencakup data sensory, bukan kesimpulan penyebab produksi. "
            + CONFOUNDING_NOTE
        ),
    }


def gen_insight_shift(sh_df: pd.DataFrame) -> dict:
    """
    Generate insight dari gap rate per shift — lensa PROSES (KimFis vs Verifikator).
    Insight ini SENGAJA dipisah dari insight pass rate (lensa OUTCOME) —
    jangan digabung jadi satu narasi, karena keduanya diukur dari hal berbeda.
    sh_df: DataFrame dengan kolom Shift_Label, Rate %, Mismatch, Total

    Metodologi 2 langkah (mencegah multiple comparison problem):
      1. Omnibus test (chi-square) — cek dulu apakah ADA beda di antara
         SEMUA shift sekaligus, sebelum nyari pasangan paling ekstrem.
      2. Kalau omnibus signifikan, baru drill-down ke pasangan worst-vs-best,
         pakai threshold Bonferroni (0.05 / jumlah pasangan) — bukan 0.05 polos,
         karena kita "nyari" pasangan ini dari banyak kemungkinan.
    """
    valid = sh_df[sh_df["Total"] >= MIN_N]
    if valid.empty:
        return {"status": "insufficient", "msg": f"Data shift terlalu sedikit (minimum n={MIN_N})."}

    worst  = valid.loc[valid["Rate %"].idxmax()]
    best   = valid.loc[valid["Rate %"].idxmin()]
    mean_r = valid["Rate %"].mean()

    observable = (
        f"Shift **{worst['Shift_Label']}** mencatat gap rate tertinggi: "
        f"**{worst['Rate %']}%** ({int(worst['Mismatch'])} gap dari {int(worst['Total'])} sampel). "
        f"Shift **{best['Shift_Label']}** terendah: {best['Rate %']}%. "
        f"Rata-rata antar shift: {mean_r:.1f}%."
    )

    # ── Langkah 1: Omnibus test — ada beda di antara SEMUA shift atau tidak? ──
    groups = [(int(r["Mismatch"]), int(r["Total"])) for _, r in valid.iterrows()]
    omnibus = _chi2_omnibus(groups)
    k = len(groups)
    n_pairs = k * (k - 1) // 2  # jumlah kemungkinan pasangan, misal 5 shift = 10 pasangan
    spread = worst["Rate %"] - best["Rate %"]

    if omnibus["p_value"] is None or omnibus["p_value"] >= 0.05:
        # Omnibus TIDAK signifikan -> berhenti di sini, jangan drill-down.
        # Nyari pasangan ekstrem setelah omnibus gagal itu yang bikin
        # "kelihatan beda" padahal cuma kebetulan cari-cari.
        inference = (
            f"Diuji ke SEMUA {k} shift sekaligus (bukan cuma pasangan yang kelihatan "
            f"paling beda) — hasilnya belum cukup bukti ada perbedaan nyata antar shift. "
            f"Selisih gap rate (**{spread:.1f}%**) kemungkinan besar variasi wajar."
        )
        action = (
            "Gap rate antar shift tidak berbeda signifikan secara keseluruhan — "
            "fokus investigasi ke faktor analis dan parameter, bukan shift."
        )
        need_action = False
    else:
        # Omnibus signifikan -> baru boleh drill-down, dengan threshold lebih
        # ketat (Bonferroni) karena pasangan ini dipilih dari banyak kemungkinan.
        alpha_corrected = 0.05 / n_pairs if n_pairs > 0 else 0.05
        pval = _ztest_pvalue(worst["Rate %"] / 100, worst["Total"],
                              best["Rate %"] / 100, best["Total"])

        if pval is not None and pval < alpha_corrected:
            inference = (
                f"Diuji ke semua {k} shift sekaligus — ADA perbedaan nyata di antaranya "
                f"(bukan kebetulan). Setelah ditelusuri, Shift {worst['Shift_Label']} vs "
                f"{best['Shift_Label']} adalah pasangan yang paling mencolok "
                f"(selisih {spread:.1f}%), dan ini tetap konsisten meski sudah "
                f"mempertimbangkan bahwa kita membandingkan banyak pasangan sekaligus."
            )
            need_action = True
        else:
            inference = (
                f"Diuji ke semua {k} shift sekaligus — ADA perbedaan nyata di antaranya. "
                f"Tapi pasangan Shift {worst['Shift_Label']} vs {best['Shift_Label']} "
                f"secara spesifik belum cukup kuat untuk disebut pasangan yang paling "
                f"beda (bisa jadi bedanya ada di kombinasi shift lain)."
            )
            need_action = False

        action = (
            f"Investigasi Shift **{worst['Shift_Label']}**: "
            f"siapa analis yang bertugas di shift ini? "
            f"Apakah ada kondisi evaluasi yang berbeda (waktu, suhu, pencahayaan)? "
            f"Gunakan section Performa Analis untuk cek komposisi analis per shift."
        ) if need_action else (
            "Ada perbedaan antar shift secara keseluruhan, tapi belum jelas shift mana "
            "yang paling bertanggung jawab — perlu data lebih banyak untuk drill-down."
        )

    confirm = (
        "Analisis ini hanya mencakup data sensory — temuan di atas adalah "
        "batas lingkup yang bisa kami olah dari data evaluasi sensory. "
        + CONFOUNDING_NOTE
    )

    return {
        "status":      "ok",
        "observable":  observable,
        "inference":   inference,
        "action":      action,
        "confirm":     confirm,
        "worst_shift": str(worst["Shift_Label"]),
        "spread":      round(spread, 1),
    }


def gen_insight_analyst_performance(perf: pd.DataFrame) -> dict:
    """
    Generate insight dari performa analis.
    perf: DataFrame dengan kolom Analis, Rate %, Mismatch, Total
    """
    valid = perf[perf["Total"] >= MIN_N]
    if valid.empty:
        return {"status": "insufficient", "msg": f"Tidak ada analis dengan ≥{MIN_N} sampel."}

    mean_r = valid["Rate %"].mean()
    std_r  = valid["Rate %"].std()
    flagged_desc = valid[valid["Rate %"] > mean_r + std_r]  # descriptive doang, bukan uji statistik
    best    = valid.loc[valid["Rate %"].idxmin()]
    worst   = valid.loc[valid["Rate %"].idxmax()]
    k       = len(valid)
    n_pairs = k * (k - 1) // 2

    observable = (
        f"**{k}** analis dievaluasi. "
        f"**{worst['Analis']}** memiliki tingkat ketidaksesuaian tertinggi "
        f"({worst['Rate %']}%, {int(worst['Mismatch'])} dari {int(worst['Total'])} sampel). "
        f"**{best['Analis']}** terendah ({best['Rate %']}%)."
    )

    # ── Omnibus test dulu: ada beda nyata di antara SEMUA analis atau tidak? ──
    groups = [(int(r["Mismatch"]), int(r["Total"])) for _, r in valid.iterrows()]
    omnibus = _chi2_omnibus(groups)

    if omnibus["p_value"] is None or omnibus["p_value"] >= 0.05:
        inference = (
            f"Diuji ke SEMUA {k} analis sekaligus — belum cukup bukti ada perbedaan "
            f"nyata antar analis. Variasi yang kelihatan (termasuk {worst['Analis']} "
            f"vs {best['Analis']}) kemungkinan besar variasi wajar, bukan pola yang "
            f"konsisten per individu."
        )
        action = (
            f"Tingkat ketidaksesuaian antar analis belum terbukti beda secara "
            f"statistik — kalibrasi sebaiknya menyasar **seluruh tim**, bukan "
            f"individu tertentu. Pertahankan sesi kalibrasi rutin."
        )
    else:
        alpha_corrected = 0.05 / n_pairs if n_pairs > 0 else 0.05
        pval = _ztest_pvalue(worst["Rate %"] / 100, worst["Total"],
                              best["Rate %"] / 100, best["Total"])
        pair_sig = pval is not None and pval < alpha_corrected

        if len(flagged_desc) > 0:
            flagged_names = ", ".join(flagged_desc.sort_values("Rate %", ascending=False)["Analis"].tolist())
            inference = (
                f"Diuji ke semua {k} analis sekaligus — ADA perbedaan nyata di "
                f"antaranya (bukan kebetulan). **{len(flagged_desc)} analis** tingkat "
                f"ketidaksesuaiannya paling jauh dari rata-rata tim: **{flagged_names}**. "
            )
        else:
            inference = (
                f"Diuji ke semua {k} analis sekaligus — ADA perbedaan nyata di "
                f"antaranya, meski tidak ada yang menonjol jauh secara deskriptif. "
            )
        inference += (
            f"Beda {worst['Analis']} vs {best['Analis']} tetap konsisten "
            + ("meski sudah mempertimbangkan banyaknya analis yang dibandingkan."
               if pair_sig else
               "secara keseluruhan, meski pasangan spesifik ini belum tentu yang paling beda.")
        )
        action = (
            f"Adakan **sesi kalibrasi tim** — fokus pada penyesuaian persepsi "
            f"antara analis dan Verifikator. "
            f"Gunakan heatmap drill-down di bawah untuk melihat pola gap "
            f"tiap analis dan jadikan bahan diskusi bersama, bukan evaluasi individu."
        )

    return {
        "status":      "ok",
        "observable":  observable,
        "inference":   inference,
        "action":      action,
        "confirm":     CONFOUNDING_NOTE,
        "worst":       worst["Analis"],
        "best":        best["Analis"],
        "flagged":     flagged_desc["Analis"].tolist(),
        "mean_rate":   round(mean_r, 1),
        "threshold":   round(mean_r + std_r, 1),
    }


def gen_insight_tendency(tend: pd.DataFrame, long_df: pd.DataFrame) -> dict:
    """
    Generate insight dari kecenderungan Longgar/Ketat/Match.
    tend: DataFrame dengan kolom Analis, Kategori, Pct
    """
    if tend.empty:
        return {"status": "insufficient", "msg": "Data kecenderungan tidak tersedia."}

    # Rata-rata per kategori
    pivot = tend.pivot_table(index="Analis", columns="Kategori", values="Pct", fill_value=0)
    avg_longgar = pivot.get("Terlalu Longgar", pd.Series([0])).mean()
    avg_ketat   = pivot.get("Terlalu Ketat",   pd.Series([0])).mean()
    avg_match   = pivot.get("Match",           pd.Series([0])).mean()

    # Siapa paling longgar (berbahaya)
    if "Terlalu Longgar" in pivot.columns:
        most_longgar = pivot["Terlalu Longgar"].idxmax()
        most_longgar_pct = pivot["Terlalu Longgar"].max()
    else:
        most_longgar = None
        most_longgar_pct = 0

    # Pola dominan (berdasarkan selisih relatif, bukan threshold absolut)
    if avg_longgar > avg_ketat * 1.5:
        pola = "Terlalu Longgar"
        pola_desc = (
            f"mayoritas analis cenderung **Terlalu Longgar** "
            f"(rata-rata {avg_longgar:.0f}% vs {avg_ketat:.0f}% Terlalu Ketat). "
            f"Standar Verifikator secara konsisten lebih ketat."
        )
    elif avg_ketat > avg_longgar * 1.5:
        pola = "Terlalu Ketat"
        pola_desc = (
            f"mayoritas analis cenderung **Terlalu Ketat** "
            f"(rata-rata {avg_ketat:.0f}% vs {avg_longgar:.0f}% Terlalu Longgar). "
            f"Analis cenderung lebih konservatif dari Verifikator."
        )
    else:
        pola = "Beragam"
        pola_desc = (
            f"tidak ada bias dominan yang konsisten "
            f"(Longgar: {avg_longgar:.0f}%, Ketat: {avg_ketat:.0f}%)."
        )

    observable = (
        f"Rata-rata tim — Match: **{avg_match:.0f}%**, "
        f"Terlalu Longgar: **{avg_longgar:.0f}%**, "
        f"Terlalu Ketat: **{avg_ketat:.0f}%**."
    )

    # Layer 2: inference — bahasa natural
    if pola == "Terlalu Longgar":
        inference = (
            f"Secara umum, analis cenderung **Terlalu Longgar** dibanding Verifikator. "
            f"Ini pola tim, bukan kesalahan beberapa orang saja — "
            f"perlu kalibrasi bersama, bukan hanya teguran individu."
        )
    elif pola == "Terlalu Ketat":
        inference = (
            f"Secara umum, analis cenderung **menilai lebih berat** dari semestinya "
            f"dibanding Verifikator. Ini bisa menyebabkan produk ditahan padahal "
            f"sebenarnya masih layak release."
        )
    else:
        inference = (
            f"Tidak ada kecenderungan tim yang dominan — "
            f"bias bervariasi antar analis, perlu ditangani per individu."
        )

    # Action — berbasis tim, tidak sebut nama individu
    action = (
        f"Lakukan **sesi screening bertingkat** untuk kalibrasi seluruh tim — "
        f"gunakan heatmap drill-down di Tab ini untuk melihat pola tiap analis "
        f"dan lihat Tab Parameter untuk parameter yang perlu difokuskan."
    )

    confirm = (
        "Analisis ini hanya mencakup data sensory — temuan di atas adalah "
        "batas lingkup yang bisa kami olah dari data evaluasi sensory."
    )

    return {
        "status":         "ok",
        "observable":     observable,
        "inference":      inference,
        "action":         action,
        "confirm":        confirm,
        "pola":           pola,
        "avg_longgar":    round(avg_longgar, 1),
        "avg_ketat":      round(avg_ketat, 1),
        "most_longgar":   most_longgar,
    }


def gen_insight_drilldown(sub: pd.DataFrame, analis: str) -> dict:
    """
    Generate insight dari heatmap drill-down per analis.
    sub: DataFrame KF_Analis, Verif_Status per analis
    """
    n = len(sub)
    if n < MIN_N:
        return {
            "status": "insufficient",
            "msg": f"⚠️ {analis}: data terlalu sedikit (n={n}, minimum {MIN_N})."
        }

    mm = sub[sub["KF_Analis"] != sub["Verif_Status"]]
    mm_n   = len(mm)
    mm_pct = round(mm_n / n * 100, 1)

    if mm_n == 0:
        return {
            "status": "perfect",
            "msg": f"✅ **{analis}**: tidak ada mismatch dari {n:,} sampel. Konsisten sempurna."
        }

    # Gap type terbanyak
    top_gap = (
        mm.groupby(["KF_Analis","Verif_Status"]).size()
        .reset_index(name="n")
        .sort_values("n", ascending=False)
        .iloc[0]
    )
    top_gap_label = f"{top_gap['KF_Analis']} → {top_gap['Verif_Status']}"
    top_gap_n     = int(top_gap["n"])

    # Arah bias individu — berbasis severity (jarak dari Pass), bukan delta linear
    mm = mm.copy()
    mm["Sev_KF"] = mm["KF_Analis"].apply(_severity)
    mm["Sev_VF"] = mm["Verif_Status"].apply(_severity)
    mm["Sev_Diff"] = mm["Sev_KF"] - mm["Sev_VF"]   # negatif = KF lebih dekat Pass (longgar)
    avg_sev_diff = mm["Sev_Diff"].mean()

    if avg_sev_diff < -0.3:
        bias_label = "cenderung **menilai lebih ringan**"
        bias_note  = "dari semestinya (Terlalu Longgar)"
    elif avg_sev_diff > 0.3:
        bias_label = "cenderung **menilai lebih berat**"
        bias_note  = "dari semestinya (Terlalu Ketat)"
    else:
        bias_label = "relatif **seimbang**"
        bias_note  = "tidak ada bias arah yang jelas"

    # TP3 alert
    tp3_gaps = mm[mm["KF_Analis"].isin(["TP 3"]) | mm["Verif_Status"].isin(["TP 3"])]
    tp3_n    = len(tp3_gaps)

    observable = (
        f"**{analis}**: {n:,} sampel · {mm_n} gap ({mm_pct}%). "
        f"Gap terbanyak: **{top_gap_label}** ({top_gap_n} kejadian). "
        f"{bias_label} ({bias_note})."
    )

    action = (
        f"Fokus feedback: pola **{top_gap_label}** ({top_gap_n}x) — "
        f"diskusikan batas antara {top_gap['KF_Analis']} dan {top_gap['Verif_Status']} "
        f"menggunakan sampel kontrol. "
        + (f"⚠️ {tp3_n} gap melibatkan TP 3 — perlu investigasi segera. " if tp3_n > 0 else "")
        + f"Lihat detail batch di **Tab Daily Report**."
    )

    return {
        "status":     "ok",
        "observable": observable,
        "action":     action,
        "top_gap":    top_gap_label,
        "top_gap_n":  top_gap_n,
        "bias":       bias_label,
        "tp3_n":      tp3_n,
        "mm_pct":     mm_pct,
    }


if __name__ == "__main__":
    print("insight_engine.py OK — semua fungsi terdefinisi")
    fns = [
        gen_insight_gap_type, gen_insight_trend,
        gen_insight_parameter, gen_insight_product,
        gen_insight_shift, gen_insight_analyst_performance,
        gen_insight_tendency, gen_insight_drilldown,
        gen_insight_quality_by_dim,
    ]
    for f in fns:
        print(f"  ✅ {f.__name__}")


# ══════════════════════════════════════════════════════════════════
# RENDER HELPER — dipakai semua tab
# ══════════════════════════════════════════════════════════════════

def render_insight_box(result: dict, context: str = "") -> None:
    """
    Render box interpretasi & action ke Streamlit.
    Struktur: observable → inference → action → confirm (disclaimer)
    """
    import streamlit as st

    if result.get("status") == "insufficient":
        st.caption(f"ℹ️ {result.get('msg', 'Data tidak cukup untuk insight.')}")
        return

    if result.get("status") == "perfect":
        st.success(result.get("msg", ""))
        return

    observable = result.get("observable", "")
    inference  = result.get("inference")
    action     = result.get("action")
    confirm    = result.get("confirm")

    parts = []
    if observable:
        parts.append(f"📊 **Dari data ini:** {observable}")
    if inference:
        parts.append(f"💡 **Insight:** {inference}")
    if action:
        parts.append(f"✅ **Rekomendasi:** {action}")

    box_content = "\n\n".join(parts)

    st.markdown(
        f"""
        <div style="background:#f0f4fb; border-left:4px solid #185FA5;
                    border-radius:8px; padding:14px 18px; margin:12px 0;
                    font-size:13px; line-height:1.75; color:#1a1a1a;">
        {box_content.replace(chr(10), "<br>")}
        </div>
        """,
        unsafe_allow_html=True,
    )

    if confirm:
        st.caption(
            f"⚠️ *Batas data sensory: {confirm}*"
        )