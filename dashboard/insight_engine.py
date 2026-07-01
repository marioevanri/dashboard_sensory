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


MIN_N = 20  # minimum sampel untuk insight reliable


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
        if top_cat in ("Beda Tingkatan", "Gap Signifikan"):
            inference = (
                f"{top_pct}% gap adalah **Beda Tingkatan** — "
                f"arah penilaian sama (kurang/lebih), tapi berbeda di levelnya. "
                f"Contoh: KimFis TP 1-, Verifikator TP 2-."
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
    action = action_map.get(top_cat, action_map.get("Beda Tingkatan", "Tinjau distribusi tipe gap dan diskusikan dengan tim QC."))

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
        action = (
            f"Bulan terakhir ({monthly.iloc[-1]['Month']}) gap rate {last_rate}% — "
            f"**lebih tinggi dari bulan sebelumnya** ({prev_rate}%). "
            f"Perlu investigasi segera: ada perubahan komposisi analis, produk, atau proses?"
        )
    elif trend_direction == "membaik":
        action = (
            f"Bulan terakhir ({monthly.iloc[-1]['Month']}) gap rate {last_rate}% — "
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
            f"ini sinyal kualitas produk yang perlu perhatian lebih, "
            f"bukan masalah kalibrasi analis."
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

def gen_insight_shift(sh_df: pd.DataFrame) -> dict:
    """
    Generate insight dari gap rate per shift.
    sh_df: DataFrame dengan kolom Shift_Label, Rate %, Mismatch, Total
    """
    valid = sh_df[sh_df["Total"] >= MIN_N]
    if valid.empty:
        return {"status": "insufficient", "msg": f"Data shift terlalu sedikit (minimum n={MIN_N})."}

    worst  = valid.loc[valid["Rate %"].idxmax()]
    best   = valid.loc[valid["Rate %"].idxmin()]
    mean_r = valid["Rate %"].mean()
    std_r  = valid["Rate %"].std()

    # Threshold relatif: "tinggi" = > mean + 0.5*std
    high_shifts = valid[valid["Rate %"] > mean_r + 0.5 * std_r]

    observable = (
        f"Shift **{worst['Shift_Label']}** mencatat gap rate tertinggi: "
        f"**{worst['Rate %']}%** ({int(worst['Mismatch'])} gap dari {int(worst['Total'])} sampel). "
        f"Shift **{best['Shift_Label']}** terendah: {best['Rate %']}%. "
        f"Rata-rata antar shift: {mean_r:.1f}%."
    )

    # Layer 2: apakah spread antar shift besar?
    spread = worst["Rate %"] - best["Rate %"]
    if spread >= 10:
        inference = (
            f"Selisih gap rate antar shift mencapai **{spread:.1f}%** — "
            f"cukup besar untuk mengindikasikan perbedaan kondisi evaluasi "
            f"atau komposisi analis yang bertugas per shift. "
            f"Perlu investigasi lebih lanjut di luar data sensory."
        )
    elif spread >= 5:
        inference = (
            f"Selisih gap rate antar shift **{spread:.1f}%** — "
            f"ada variasi antar shift tapi tidak ekstrem. "
            f"Pantau terus apakah pola ini konsisten di bulan berikutnya."
        )
    else:
        inference = (
            f"Gap rate antar shift relatif merata (selisih {spread:.1f}%) — "
            f"perbedaan shift bukan faktor dominan. "
            f"Penyebab lebih mungkin ada di faktor lain (analis, produk, atau periode)."
        )

    action = (
        f"Investigasi Shift **{worst['Shift_Label']}**: "
        f"siapa analis yang bertugas di shift ini? "
        f"Apakah ada kondisi evaluasi yang berbeda (waktu, suhu, pencahayaan)? "
        f"Gunakan Tab Performa Analis untuk cek komposisi analis per shift."
    ) if spread >= 5 else (
        "Gap rate antar shift tidak berbeda signifikan — "
        "fokus investigasi ke faktor analis dan parameter, bukan shift."
    )

    confirm = (
        "Analisis ini hanya mencakup data sensory — temuan di atas adalah "
        "batas lingkup yang bisa kami olah dari data evaluasi sensory."
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
    # Threshold relatif: "perlu perhatian" = > mean + 1*std
    flagged = valid[valid["Rate %"] > mean_r + std_r]
    best    = valid.loc[valid["Rate %"].idxmin()]
    worst   = valid.loc[valid["Rate %"].idxmax()]

    observable = (
        f"**{len(valid)}** analis dievaluasi. "
        f"**{worst['Analis']}** memiliki tingkat ketidaksesuaian tertinggi "
        f"({worst['Rate %']}%, {int(worst['Mismatch'])} dari {int(worst['Total'])} sampel). "
        f"**{best['Analis']}** terendah ({best['Rate %']}%)."
    )

    # Layer 2
    if len(flagged) > 0:
        flagged_names = ", ".join(flagged.sort_values("Rate %", ascending=False)["Analis"].tolist())
        inference = (
            f"**{len(flagged)} analis** memiliki tingkat ketidaksesuaian yang "
            f"menonjol dibanding rata-rata tim: **{flagged_names}**."
        )
    else:
        inference = (
            f"Tidak ada analis yang menonjol jauh di atas yang lain — "
            f"tingkat ketidaksesuaian relatif merata di antara semua analis."
        )

    # Action — berbasis tim, bukan individu
    if len(flagged) > 0:
        action = (
            f"Adakan **sesi kalibrasi tim** — fokus pada penyesuaian persepsi "
            f"antara analis dan Verifikator. "
            f"Gunakan heatmap drill-down di bawah untuk melihat pola gap "
            f"tiap analis dan jadikan bahan diskusi bersama, bukan evaluasi individu."
        )
    else:
        action = (
            f"Tingkat ketidaksesuaian antar analis relatif merata — "
            f"pertahankan dengan sesi kalibrasi rutin."
        )

    return {
        "status":      "ok",
        "observable":  observable,
        "inference":   inference,
        "action":      action,
        "worst":       worst["Analis"],
        "best":        best["Analis"],
        "flagged":     flagged["Analis"].tolist(),
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