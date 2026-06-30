"""tab4_shift_analyst.py — Shift & Performa Analis."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import STATUS_ORDER, STATUS_COLORS, STATUS_NUM, PARAM_COLS, PARAM_LABELS
from insight_engine import (
    gen_insight_shift, gen_insight_analyst_performance,
    gen_insight_tendency, gen_insight_drilldown,
    render_insight_box,
)

MIN_ANALYST_SAMPLE = 20  # Minimum sampel agar performa analis representatif


def _norm_shift(v) -> str:
    s = str(v).strip()
    try:
        f = float(s)
        if f == int(f): return str(int(f))
    except: pass
    return s

SHIFT_ORDER_LIST = ["1", "1-2", "2", "2-3", "3"]


def render(df: pd.DataFrame) -> None:
    """Render Tab 4 — Shift & Performa Analis."""
    st.subheader("Shift & Performa Analis")

    df_s = df.copy()
    df_s["Shift_Label"] = df_s["Shift_Code"].apply(_norm_shift)

    # Hitung angka untuk pengantar
    df_mm   = df_s[df_s["Comparison"] == "MISMATCH"]
    df_verif = df_s[df_s["Comparison"].isin(["MATCH","MISMATCH"])]
    total_mm = len(df_mm)
    gap_rate = total_mm / len(df_verif) * 100 if len(df_verif) else 0

    # Shift terburuk
    sh_df = (
        df_verif.groupby("Shift_Label")
        .agg(Total=("Comparison","count"),
             Mismatch=("Comparison", lambda x: (x=="MISMATCH").sum()))
        .reset_index()
    )
    sh_df["Rate %"] = (sh_df["Mismatch"] / sh_df["Total"] * 100).round(1)
    worst_shift = sh_df.loc[sh_df["Rate %"].idxmax()] if not sh_df.empty else None

    # ── Pengantar storytelling ────────────────────────────────────
    worst_shift_text = (
        f"Shift <b>{worst_shift['Shift_Label']}</b> "
        f"({worst_shift['Rate %']}% gap rate)"
        if worst_shift is not None else "—"
    )
    st.markdown(
        f"""
        <div style="background:#f8f9fa; border-left:4px solid #185FA5;
                    border-radius:8px; padding:14px 18px; margin-bottom:16px;
                    font-size:14px; color:#1a1a1a; line-height:1.8;">
        Di Tab Parameter terlihat <b>Creamy</b> adalah parameter paling kritis.
        &nbsp; Tab ini menjawab dua pertanyaan lanjutan:
        <b>shift mana yang paling banyak gap?</b>
        &nbsp;·&nbsp;
        <b>analis mana yang paling sering beda dengan Verifikator dan bagaimana polanya?</b>
        <br>
        <span style="font-size:12px; color:#888;">
        Dari {len(df_verif):,} sampel terverifikasi —
        {total_mm:,} gap ({gap_rate:.1f}%) ·
        Shift tertinggi: {worst_shift_text}
        </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Section 1: Gap Rate per Shift ────────────────────────────
    st.subheader("Gap Rate per Shift")
    st.caption("Dari Tab Gap Analysis: ringkasan gap rate per shift. Detail investigasi ada di bawah.")
    _render_shift_summary(sh_df)

    st.divider()

    # ── Section 2: Performa Analis ────────────────────────────────
    st.subheader("Performa Analis vs Verifikator")
    st.caption(
        f"Mismatch rate setiap analis terhadap penilaian Verifikator. "
        f"Minimum {MIN_ANALYST_SAMPLE} sampel untuk ditampilkan."
    )
    _render_analyst_performance(df_s)

    st.divider()

    # ── Section 3: Kecenderungan Analis ──────────────────────────
    st.subheader("Kecenderungan Penilaian Analis")
    st.caption(
        "Apakah analis cenderung **Terlalu Longgar** (menilai lebih dekat ke Pass), "
        "**Terlalu Ketat** (menilai lebih jauh dari Pass), atau **Match**? "
        "Ini menunjukkan bias sistematis tiap analis."
    )
    _render_analyst_tendency(df_s)

    st.divider()

    # ── Section 4: Drill-down per analis ─────────────────────────
    st.subheader("Drill-down per Analis")
    st.caption("Heatmap penilaian analis vs Verifikator — baris = analis, kolom = Verifikator.")
    _render_analyst_drilldown(df_s)


# ── Sub-renderers ─────────────────────────────────────────────────

def _render_shift_summary(sh_df: pd.DataFrame) -> None:
    """Bar chart gap rate per shift — 1 chart saja, bersih."""
    if sh_df.empty:
        st.info("Data shift tidak tersedia.")
        return

    max_rate = sh_df["Rate %"].max()
    sh_df["Color"] = sh_df["Rate %"].apply(
        lambda x: "#D32F2F" if x == max_rate else "#185FA5"
    )
    sh_df["Label"] = sh_df.apply(
        lambda r: f"{r['Rate %']}%  ({int(r['Mismatch'])} dari {int(r['Total'])})", axis=1
    )
    sh_df["Shift_Label"] = pd.Categorical(
        sh_df["Shift_Label"], SHIFT_ORDER_LIST, ordered=True
    )
    sh_df = sh_df.sort_values("Shift_Label")

    fig = go.Figure()
    for _, row in sh_df.iterrows():
        fig.add_trace(go.Bar(
            x=[row["Rate %"]], y=[row["Shift_Label"]],
            orientation="h",
            text=[row["Label"]],
            textposition="inside",
            insidetextanchor="middle",
            marker_color=row["Color"],
            showlegend=False,
        ))
    fig.update_layout(
        template="plotly_white", height=220,
        margin=dict(t=10, b=10, l=10, r=20),
        xaxis=dict(title="Gap Rate (%)", range=[0, 50]),
        yaxis=dict(title="Shift"),
        barmode="stack",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Caption insight
    worst = sh_df.loc[sh_df["Rate %"].idxmax()]
    best  = sh_df.loc[sh_df["Rate %"].idxmin()]
    st.caption(
        f"🔴 Shift **{worst['Shift_Label']}** gap rate tertinggi: {worst['Rate %']}% "
        f"({int(worst['Mismatch'])} gap dari {int(worst['Total'])} sampel). &nbsp;&nbsp;"
        f"🟢 Shift **{best['Shift_Label']}** gap rate terendah: {best['Rate %']}%."
    )

    # Insight box
    render_insight_box(gen_insight_shift(sh_df), context="shift")


def _render_analyst_performance(df_s: pd.DataFrame) -> None:
    """Bar chart mismatch rate semua analis (min 20 sampel)."""
    # Rebuild long-format dari A1/A2/A3 per batch
    records = []
    df_verif = df_s[df_s["Comparison"].isin(["MATCH","MISMATCH"])].copy()

    for no in [1, 2, 3]:
        name_col   = f"A{no}_Name"
        status_col = f"A{no}_Status"
        if name_col not in df_verif.columns: continue

        sub = df_verif[[name_col, status_col, "Verif_Status"]].dropna(subset=[name_col])
        sub = sub[sub[name_col].astype(str).str.strip().str.lower() != "nan"]
        sub = sub.rename(columns={name_col:"Analis", status_col:"KF_Status_Analis"})
        records.append(sub)

    if not records:
        st.info("Data analis tidak tersedia.")
        return

    long_df = pd.concat(records, ignore_index=True)
    long_df["Is_Mismatch"] = long_df["KF_Status_Analis"] != long_df["Verif_Status"]
    # Fix 3: Title Case nama analis
    long_df["Analis"] = long_df["Analis"].str.strip().str.title()

    perf = (
        long_df.groupby("Analis")
        .agg(Total=("Is_Mismatch","count"),
             Mismatch=("Is_Mismatch","sum"))
        .reset_index()
    )
    perf["Rate %"] = (perf["Mismatch"] / perf["Total"] * 100).round(1)
    perf = perf[perf["Total"] >= MIN_ANALYST_SAMPLE]
    perf = perf.sort_values("Rate %", ascending=False)
    perf["Label"] = perf.apply(
        lambda r: f"{r['Rate %']}%  |  {int(r['Mismatch'])} dari {int(r['Total'])}", axis=1
    )

    # Warna gradient
    max_r = perf["Rate %"].max()
    min_r = perf["Rate %"].min()

    fig = go.Figure()
    for _, row in perf.iterrows():
        norm = (row["Rate %"] - min_r) / (max_r - min_r + 0.001)
        r = int(211 * norm + 24 * (1 - norm))
        g = int(47  * norm + 95 * (1 - norm))
        b = int(47  * norm + 165 * (1 - norm))
        color = f"rgb({r},{g},{b})"
        fig.add_trace(go.Bar(
            x=[row["Rate %"]], y=[row["Analis"]],
            orientation="h",
            text=[row["Label"]],
            textposition="inside",
            insidetextanchor="middle",
            marker_color=color,
            showlegend=False,
        ))
    fig.update_layout(
        template="plotly_white",
        height=max(300, len(perf) * 32),
        margin=dict(t=10, b=10, l=10, r=20),
        xaxis=dict(title="Gap Rate (%)", range=[0, max_r * 1.2]),
        yaxis=dict(title="Analis", autorange="reversed"),
        barmode="stack",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Small sample note
    st.caption(
        "* Analis dengan < 100 sampel hasilnya kurang stabil secara statistik "
        "— interpretasikan dengan hati-hati."
    )

    # Insight box — threshold relatif, n= selalu ada
    render_insight_box(gen_insight_analyst_performance(perf), context="analyst_perf")


def _render_analyst_tendency(df_s: pd.DataFrame) -> None:
    """Stacked bar horizontal kecenderungan analis."""
    records = []
    df_verif = df_s[df_s["Comparison"].isin(["MATCH","MISMATCH"])].copy()

    for no in [1, 2, 3]:
        name_col   = f"A{no}_Name"
        status_col = f"A{no}_Status"
        if name_col not in df_verif.columns: continue
        sub = df_verif[[name_col, status_col, "Verif_Status"]].dropna(subset=[name_col])
        sub = sub[sub[name_col].astype(str).str.strip().str.lower() != "nan"]
        sub = sub.rename(columns={name_col:"Analis", status_col:"KF_Status_Analis"})
        records.append(sub)

    if not records:
        st.info("Data analis tidak tersedia.")
        return

    long_df = pd.concat(records, ignore_index=True)
    long_df = long_df[long_df["Verif_Status"].notna() & long_df["KF_Status_Analis"].notna()]
    # Title Case
    long_df["Analis"] = long_df["Analis"].str.strip().str.title()

    def categorize(row):
        kf = row["KF_Status_Analis"]
        vf = row["Verif_Status"]
        if kf == vf:
            return "Match"
        # Severity = jarak dari Pass (makin kecil makin baik). TP3 selalu terparah.
        SEV = {"Pass": 0, "TP 1-": 1, "TP 1+": 1, "TP 2-": 2, "TP 2+": 2, "TP 3": 99}
        sev_kf = SEV.get(kf, 0)
        sev_vf = SEV.get(vf, 0)
        if sev_kf < sev_vf:
            return "Terlalu Longgar"  # analis lebih dekat Pass dari Verifikator
        elif sev_kf > sev_vf:
            return "Terlalu Ketat"    # analis lebih jauh dari Pass dari Verifikator
        return "Beda Deviasi"  # severity sama tapi beda arah (mis. TP 1- vs TP 1+)

    long_df["Kategori"] = long_df.apply(categorize, axis=1)

    tend = (
        long_df.groupby(["Analis","Kategori"]).size().reset_index(name="n")
    )
    total = tend.groupby("Analis")["n"].sum().reset_index(name="Total")
    tend  = tend.merge(total, on="Analis")
    tend["Pct"] = (tend["n"] / tend["Total"] * 100).round(1)
    tend = tend[tend["Total"] >= MIN_ANALYST_SAMPLE]

    # Urut by Match % desc
    match_order = (
        tend[tend["Kategori"]=="Match"]
        .sort_values("Pct", ascending=True)["Analis"].tolist()
    )

    CAT_COLORS_TEND = {
        "Match":           "#2E8B57",
        "Terlalu Longgar": "#4DA6FF",
        "Terlalu Ketat":   "#D32F2F",
        "Beda Deviasi":    "#EF9F27",
    }
    CAT_ORDER = ["Match","Terlalu Longgar","Terlalu Ketat","Beda Deviasi"]

    fig = go.Figure()
    for cat in CAT_ORDER:
        sub = tend[tend["Kategori"] == cat]
        fig.add_trace(go.Bar(
            x=sub["Pct"], y=sub["Analis"],
            name=cat,
            orientation="h",
            text=sub["Pct"].apply(lambda x: f"{x}%" if x >= 5 else ""),
            textposition="inside",
            insidetextanchor="middle",
            marker_color=CAT_COLORS_TEND[cat],
        ))
    fig.update_layout(
        barmode="stack",
        template="plotly_white",
        height=max(300, len(match_order) * 28),
        margin=dict(t=10, b=40, l=10, r=20),
        xaxis=dict(title="Proporsi (%)", range=[0,100]),
        yaxis=dict(
            title="Analis",
            categoryorder="array",
            categoryarray=match_order,
        ),
        legend=dict(orientation="h", y=-0.12),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Definisi Terlalu Longgar/Ketat — berbasis jarak dari Pass (severity)
    st.markdown(
        """
        <div style="font-size:12px; color:#555; background:#f8f9fa;
                    border-radius:6px; padding:8px 12px; margin-bottom:8px;">
        📖 <b>Terlalu Longgar</b> = analis menilai produk <i>lebih dekat ke Pass</i> dibanding Verifikator
        (contoh: analis Pass, Verifikator TP 1-; atau analis TP 1+, Verifikator TP 2+) —
        <b style="color:#D32F2F">lebih berisiko</b> karena produk bermasalah bisa terlewat. &nbsp;|&nbsp;
        <b>Terlalu Ketat</b> = analis menilai produk <i>lebih jauh dari Pass</i> dibanding Verifikator
        (contoh: analis TP 1-, Verifikator Pass; atau analis TP 1+, Verifikator Pass).
        <br><span style="color:#888;">Penilaian berdasarkan jarak ke Pass, bukan arah kurang/lebih —
        TP 1+ dan TP 1- dianggap sama-sama "1 tingkat dari Pass".</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Insight otomatis — individu + pola dominan
    match_pct   = tend[tend["Kategori"]=="Match"].set_index("Analis")["Pct"]
    longgar_pct = tend[tend["Kategori"]=="Terlalu Longgar"].set_index("Analis")["Pct"]
    ketat_pct   = tend[tend["Kategori"]=="Terlalu Ketat"].set_index("Analis")["Pct"]

    if not match_pct.empty:
        best_analis  = match_pct.idxmax()
        worst_analis = match_pct.idxmin()

        longgar_worst = longgar_pct.get(worst_analis, 0)
        ketat_worst   = ketat_pct.get(worst_analis, 0)
        bias = "terlalu longgar" if longgar_worst > ketat_worst else "terlalu ketat"

        # Pola dominan keseluruhan
        avg_longgar = longgar_pct.mean() if not longgar_pct.empty else 0
        avg_ketat   = ketat_pct.mean()   if not ketat_pct.empty   else 0
        if avg_longgar > avg_ketat * 1.5:
            pola_text = (
                f"Pola umum: mayoritas analis cenderung **Terlalu Longgar** "
                f"(rata-rata {avg_longgar:.0f}% vs {avg_ketat:.0f}% Terlalu Ketat) — "
                f"standar Verifikator secara konsisten lebih ketat dari analis."
            )
        elif avg_ketat > avg_longgar * 1.5:
            pola_text = (
                f"Pola umum: mayoritas analis cenderung **Terlalu Ketat** "
                f"(rata-rata {avg_ketat:.0f}% vs {avg_longgar:.0f}% Terlalu Longgar)."
            )
        else:
            pola_text = (
                f"Pola beragam — tidak ada bias dominan yang konsisten di seluruh analis "
                f"(Longgar: {avg_longgar:.0f}%, Ketat: {avg_ketat:.0f}% rata-rata)."
            )

        st.info(
            f"💡 **{best_analis}** paling konsisten dengan Verifikator "
            f"({match_pct[best_analis]:.0f}% Match). &nbsp;&nbsp;"
            f"**{worst_analis}** paling sering berbeda "
            f"({100 - match_pct[worst_analis]:.0f}% tidak match) — "
            f"cenderung **{bias}**. &nbsp;&nbsp;"
            f"{pola_text}"
        )

    # Insight box dari engine — threshold relatif, batas data jelas
    render_insight_box(gen_insight_tendency(tend, long_df), context="tendency")


def _render_analyst_drilldown(df_s: pd.DataFrame) -> None:
    """Heatmap KF vs Verifikator per analis yang dipilih."""
    records = []
    df_verif = df_s[df_s["Verif_Status"].notna()].copy()

    for no in [1, 2, 3]:
        name_col   = f"A{no}_Name"
        status_col = f"A{no}_Status"
        if name_col not in df_verif.columns: continue
        sub = df_verif[[name_col, status_col, "Verif_Status"]].dropna(subset=[name_col])
        sub = sub[sub[name_col].astype(str).str.strip().str.lower() != "nan"]
        sub = sub.rename(columns={name_col:"Analis", status_col:"KF_Analis"})
        sub["Analis"] = sub["Analis"].str.strip().str.title()
        records.append(sub)

    if not records:
        st.info("Data tidak tersedia.")
        return

    long_df  = pd.concat(records, ignore_index=True)
    analysts = sorted(
        long_df.groupby("Analis").size()
        .loc[lambda s: s >= MIN_ANALYST_SAMPLE].index.tolist()
    )

    if not analysts:
        st.info(f"Tidak ada analis dengan ≥{MIN_ANALYST_SAMPLE} sampel.")
        return

    sel = st.selectbox("Pilih Analis:", analysts, key="analyst_drilldown")

    sub = long_df[long_df["Analis"] == sel]
    heat = (
        sub.groupby(["KF_Analis","Verif_Status"]).size()
        .reset_index(name="n")
    )
    piv = heat.pivot_table(
        index="KF_Analis", columns="Verif_Status",
        values="n", fill_value=0
    )
    rows = [s for s in STATUS_ORDER if s in piv.index]
    cols = [s for s in STATUS_ORDER if s in piv.columns]
    piv  = piv.loc[rows, cols]

    import numpy as np
    total_s = sub.shape[0]
    mm_s    = (sub["KF_Analis"] != sub["Verif_Status"]).sum()

    fig = px.imshow(
        piv, text_auto=True, aspect="auto",
        color_continuous_scale=["#EBF4FF","#1565C0"],
        template="plotly_white",
        labels={"x":"Status Verifikator (Ground Truth)", "y":"Status Analis"},
        height=350,
    )
    # Highlight diagonal (match) dengan border hijau
    for i, r in enumerate(rows):
        if r in cols:
            j = cols.index(r)
            fig.add_shape(
                type="rect",
                x0=j-0.5, x1=j+0.5, y0=i-0.5, y1=i+0.5,
                line=dict(color="#2E8B57", width=2.5),
            )
    fig.update_layout(
        margin=dict(t=30, b=40, l=10, r=10),
        coloraxis_showscale=False,
    )
    fig.update_xaxes(side="bottom")
    st.markdown(f"**{sel}** — {total_s:,} sampel terverifikasi · {mm_s} gap ({mm_s/total_s*100:.1f}%)")
    st.caption("Diagonal hijau = match. Off-diagonal = gap.")
    st.plotly_chart(fig, use_container_width=True)

    # Alert TP 3 gap
    tp3_gaps = sub[
        (sub["KF_Analis"] != sub["Verif_Status"]) &
        (sub["KF_Analis"].isin(["TP 3"]) | sub["Verif_Status"].isin(["TP 3"]))
    ]
    if len(tp3_gaps) > 0:
        st.warning(
            f"⚠️ **{len(tp3_gaps)} gap melibatkan TP 3** — analis dan Verifikator berbeda "
            f"di level off-taste. Ini kritis dan perlu investigasi segera."
        )

    # Insight box dari engine
    render_insight_box(gen_insight_drilldown(sub, sel), context="drilldown")

    st.markdown(
        """
        <div style="font-size:12px; color:#666; margin-top:8px;">
        💡 <b>Lanjutkan investigasi:</b>
        &nbsp; 📋 <b>Tab Daily Report</b> — lihat detail batch spesifik
        yang melibatkan analis ini untuk keputusan release.
        </div>
        """,
        unsafe_allow_html=True,
    )
