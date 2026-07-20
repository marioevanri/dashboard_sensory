"""
tab6_case_study.py — Case Study: dari Overview sampai Rekomendasi.
====================================================================
Halaman ini merangkai temuan dari Tab 1-5 jadi SATU cerita utuh untuk
1 produk — dipakai sebagai contoh nyata untuk submission Kaizen /
portofolio, biar reviewer lihat end-to-end value dashboard, bukan
cuma fitur per tab.

Alur cerita: Latar Belakang & Masalah -> Temuan Data -> Root Cause
-> Rekomendasi -> Dampak yang Diharapkan.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import STATUS_ORDER, STATUS_COLORS, PARAM_COLS, PARAM_LABELS

MIN_N = 20


def render(df: pd.DataFrame) -> None:
    """Render Tab 6 — Case Study."""
    st.subheader("📌 Case Study — Dari Data ke Rekomendasi")
    st.caption(
        "Satu produk, ditelusuri utuh dari gejala sampai rekomendasi — "
        "contoh konkret bagaimana dashboard ini dipakai untuk keputusan nyata."
    )

    # ── Pilih produk case study ───────────────────────────────────
    verif_df = df[df["Verif_Status"].notna()].copy()
    prod_n = verif_df.groupby("Product_Name").size()
    eligible = sorted(prod_n[prod_n >= MIN_N].index.tolist())

    if not eligible:
        st.info(f"Belum ada produk dengan ≥{MIN_N} sampel terverifikasi pada filter saat ini.")
        return

    default_prod = "LAUTAN KRIMER LK 32 AB" if "LAUTAN KRIMER LK 32 AB" in eligible else eligible[0]
    sel_prod = st.selectbox(
        "Pilih produk untuk case study",
        eligible,
        index=eligible.index(default_prod),
        key="case_study_product",
    )

    pdf = verif_df[verif_df["Product_Name"] == sel_prod].copy()
    n_total = len(pdf)
    n_pass  = (pdf["Verif_Status"] == "Pass").sum()
    n_tp1   = pdf["Verif_Status"].isin(["TP 1-", "TP 1+"]).sum()
    n_tp2   = pdf["Verif_Status"].isin(["TP 2-", "TP 2+"]).sum()
    n_tp3   = (pdf["Verif_Status"] == "TP 3").sum()
    pass_rate = round(n_pass / n_total * 100, 1)
    tp_rate   = round((n_total - n_pass) / n_total * 100, 1)

    both = pdf[pdf["Comparison"].isin(["MATCH", "MISMATCH"])]
    gap_n    = (both["Comparison"] == "MISMATCH").sum()
    gap_rate = round(gap_n / len(both) * 100, 1) if len(both) > 0 else 0

    # ── Parameter penyebab TP terbanyak ───────────────────────────
    param_rows = []
    for p in PARAM_COLS:
        vcol = f"V_{p}_Status"
        if vcol not in pdf.columns:
            continue
        n_tp_p = (pdf[vcol].notna() & (pdf[vcol] != "Pass")).sum()
        if n_tp_p > 0:
            param_rows.append({"Parameter": PARAM_LABELS.get(p, p), "Jumlah TP": int(n_tp_p)})
    param_df = pd.DataFrame(param_rows).sort_values("Jumlah TP", ascending=False)
    top_param = param_df.iloc[0]["Parameter"] if not param_df.empty else None
    top_param_n = int(param_df.iloc[0]["Jumlah TP"]) if not param_df.empty else 0
    top_param_pct = round(top_param_n / n_total * 100, 1) if top_param and n_total > 0 else 0

    # ── Parameter dominan company-wide (semua produk, bukan cuma produk ini) ──
    company_rows = []
    for p in PARAM_COLS:
        vcol = f"V_{p}_Status"
        if vcol not in verif_df.columns:
            continue
        n_tp_c = (verif_df[vcol].notna() & (verif_df[vcol] != "Pass")).sum()
        if n_tp_c > 0:
            company_rows.append({"Parameter": PARAM_LABELS.get(p, p), "Jumlah TP": int(n_tp_c)})
    company_df = pd.DataFrame(company_rows).sort_values("Jumlah TP", ascending=False)
    company_top_param = company_df.iloc[0]["Parameter"] if not company_df.empty else None
    company_top_n = int(company_df.iloc[0]["Jumlah TP"]) if not company_df.empty else 0
    company_verif_n = len(verif_df)

    # ══════════════════════════════════════════════════════════════
    # 1. LATAR BELAKANG & MASALAH
    # ══════════════════════════════════════════════════════════════
    st.markdown("### 1️⃣ Latar Belakang & Masalah")
    st.markdown(
        f"""
        <div style="background:#f8f9fa; border-left:4px solid #185FA5;
                    border-radius:8px; padding:14px 18px; margin-bottom:12px;
                    font-size:14px; color:#1a1a1a; line-height:1.85;">
        PT Lautan Natural Krimerindo punya 2 KPI sensory yang bersifat mutlak:
        <b>0 komplain customer</b> dan <b>100% approval untuk sampel preshipment/eksport</b>.
        Kedua KPI ini nggak bisa dicapai kalau proses evaluasi sensory sendiri
        nggak akurat — karena itu, gap antara penilaian KimFis (3 analis) dan
        Verifikator (ground truth) dianggap krusial, bukan sekadar selisih angka.
        <br><br>
        Produk <b>{sel_prod}</b> dipilih sebagai case study karena termasuk produk
        dengan performa yang butuh perhatian — dari {n_total:,} sampel terverifikasi,
        cuma <b>{pass_rate}%</b> yang Pass.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ══════════════════════════════════════════════════════════════
    # 2. TEMUAN DATA
    # ══════════════════════════════════════════════════════════════
    st.markdown("### 2️⃣ Temuan Data")

    kpi_cols = st.columns(4)
    kpis = [
        ("Total Sampel Terverifikasi", f"{n_total:,}", "#185FA5"),
        ("Pass Rate", f"{pass_rate}%", "#2E8B57" if pass_rate >= 80 else "#D32F2F"),
        ("TP Rate", f"{tp_rate}%", "#D32F2F" if tp_rate >= 50 else "#E65100"),
        ("Gap Rate (KimFis vs Verif)", f"{gap_rate}%", "#185FA5"),
    ]
    for col, (label, val, color) in zip(kpi_cols, kpis):
        with col:
            st.markdown(
                f"""
                <div style="background:#f8f9fa; border-radius:8px; padding:12px;
                            border-top:3px solid {color}; text-align:center;">
                    <div style="font-size:11px; color:#888;">{label}</div>
                    <div style="font-size:24px; font-weight:700; color:{color};">{val}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("")
    col_l, col_r = st.columns(2)

    with col_l:
        st.caption("**Distribusi Status (Verifikator — ground truth)**")
        dist = (
            pdf["Verif_Status"].value_counts()
            .reindex(STATUS_ORDER).dropna().reset_index()
        )
        dist.columns = ["Status", "Jumlah"]
        dist["Persen"] = (dist["Jumlah"] / n_total * 100).round(1)
        fig_dist = go.Figure(go.Bar(
            x=dist["Status"], y=dist["Persen"],
            text=dist.apply(lambda r: f"{r['Persen']}%<br>({int(r['Jumlah'])})", axis=1),
            textposition="outside",
            marker_color=[STATUS_COLORS.get(s, "#aaa") for s in dist["Status"]],
        ))
        fig_dist.update_layout(
            template="plotly_white", height=320,
            margin=dict(t=20, b=20, l=10, r=10),
            yaxis=dict(title="% dari total", range=[0, dist["Persen"].max()*1.3 if not dist.empty else 100]),
            xaxis=dict(title=""),
        )
        st.plotly_chart(fig_dist, use_container_width=True)

    with col_r:
        st.caption("**Trend Pass Rate Bulanan**")
        pdf["Month"] = pd.to_datetime(pdf["Date"], errors="coerce").dt.to_period("M").astype(str)
        trend = (
            pdf.groupby("Month")
            .agg(Total=("Verif_Status", "count"),
                 Pass=("Verif_Status", lambda x: (x == "Pass").sum()))
            .reset_index()
        )
        trend["Pass Rate %"] = (trend["Pass"] / trend["Total"] * 100).round(1)
        fig_trend = go.Figure()
        fig_trend.add_trace(go.Scatter(
            x=trend["Month"], y=trend["Pass Rate %"],
            mode="lines+markers+text",
            text=trend["Pass Rate %"].apply(lambda x: f"{x}%"),
            textposition="top center",
            line=dict(color="#2E8B57", width=2),
        ))
        fig_trend.add_hline(y=100, line_dash="dot", line_color="#888",
                             annotation_text="Target 100%", annotation_position="top left")
        fig_trend.update_layout(
            template="plotly_white", height=320,
            margin=dict(t=20, b=20, l=10, r=10),
            yaxis=dict(title="Pass Rate %", range=[0, 105]),
            xaxis=dict(title=""),
        )
        st.plotly_chart(fig_trend, use_container_width=True)

    if not param_df.empty:
        st.caption("**Parameter penyebab TP**")
        fig_param = go.Figure(go.Bar(
            x=param_df["Jumlah TP"], y=param_df["Parameter"],
            orientation="h",
            text=param_df["Jumlah TP"],
            textposition="outside",
            marker_color="#D32F2F",
        ))
        fig_param.update_layout(
            template="plotly_white", height=max(220, len(param_df)*40),
            margin=dict(t=10, b=10, l=10, r=40),
            xaxis=dict(title="Jumlah TP"), yaxis=dict(title="", autorange="reversed"),
        )
        st.plotly_chart(fig_param, use_container_width=True)

    # ══════════════════════════════════════════════════════════════
    # 3. ROOT CAUSE
    # ══════════════════════════════════════════════════════════════
    st.markdown("### 3️⃣ Root Cause")
    if top_param:
        rc_text = (
            f"<b>{top_param}</b> adalah parameter penyebab TP terbanyak — "
            f"{top_param_n} dari {n_total:,} sampel ({top_param_pct}%) TP karena parameter ini. "
            f"KimFis dan Verifikator <b>sama-sama mendeteksi TP tinggi</b> di produk ini — "
            f"gap rate {gap_rate}% di sini cuma soal beda level penilaian, bukan soal "
            f"ada-tidaknya masalah (dua-duanya kompak bilang produk ini banyak TP). Ini "
            f"memperkuat bahwa masalahnya ada di <b>produk/proses produksi</b>, bukan "
            f"sekadar beda persepsi evaluasi antara KimFis dan Verifikator."
        )
        if company_top_param and company_top_param == top_param:
            rc_text += (
                f"<br><br><b>{top_param}</b> juga jadi parameter penyebab TP terbanyak di "
                f"<b>produk kita secara keseluruhan</b> ({company_top_n:,} TP dari "
                f"{company_verif_n:,} sampel terverifikasi) — temuan di produk ini "
                f"kemungkinan mencerminkan pola yang lebih luas, bukan cuma masalah 1 produk. "
                f"Worth diinvestigasi di level company-wide, bukan cuma produk ini."
            )
    else:
        rc_text = "Belum ada parameter dominan yang menonjol sebagai penyebab TP di produk ini."

    st.markdown(
        f"""
        <div style="background:#fff8e1; border-left:4px solid #E65100;
                    border-radius:8px; padding:14px 18px; margin-bottom:12px;
                    font-size:14px; color:#1a1a1a; line-height:1.85;">
        {rc_text}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ══════════════════════════════════════════════════════════════
    # 4. REKOMENDASI & RENCANA AKSI
    # ══════════════════════════════════════════════════════════════
    st.markdown("### 4️⃣ Rekomendasi & Rencana Aksi")
    if pass_rate < 50:
        urgensi = "🔴 Prioritas tinggi"
    elif pass_rate < 80:
        urgensi = "🟠 Prioritas sedang"
    else:
        urgensi = "🟢 Prioritas rendah — pantau rutin"

    # Deteksi anomali bulanan — bulan dengan pass rate jauh di bawah bulan lain
    anomaly_line = ""
    if len(trend) >= 3:
        worst_row = trend.loc[trend["Pass Rate %"].idxmin()]
        rest_mean = trend[trend["Month"] != worst_row["Month"]]["Pass Rate %"].mean()
        if worst_row["Total"] >= 5 and (rest_mean - worst_row["Pass Rate %"]) >= 15:
            anomaly_line = (
                f"<br>5. <b>Anomali terdeteksi: {worst_row['Month']}</b> — pass rate anjlok "
                f"ke {worst_row['Pass Rate %']}% (rata-rata bulan lain {rest_mean:.1f}%). "
                f"Tarik daftar batch {sel_prod} bulan itu (tersedia di Tab Daily Report), "
                f"serahkan ke Produksi/R&D dengan pertanyaan spesifik: apa yang beda di "
                f"bulan itu (bahan baku, mesin, operator)?"
            )

    st.markdown(
        f"""
        <div style="background:#f0f4fb; border-left:4px solid #185FA5;
                    border-radius:8px; padding:14px 18px; margin-bottom:12px;
                    font-size:14px; color:#1a1a1a; line-height:1.85;">
        <b>Urgensi: {urgensi}</b><br><br>
        <i>Scope QC Verifikator: deteksi pola dan sediakan bukti kuantitatif — analisis
        akar penyebab di luar data sensory (bahan baku, formula, mesin) di luar
        cakupan QC dan diteruskan ke fungsi terkait.</i><br><br>
        1. <b>Serahkan bukti ke Produksi/R&D</b>: parameter <b>{top_param or '-'}</b>
        adalah penyebab TP terbanyak di produk ini — daftar batch spesifik tersedia di
        Tab Daily Report untuk cross-reference dengan data proses mereka.<br>
        2. <b>Bandingkan dengan produk sejenis</b> yang pass rate-nya lebih tinggi —
        gunakan selector produk di atas untuk cek apakah pola parameter penyebabnya sama.<br>
        3. <b>Kalau produk ini masuk kategori preshipment/eksport</b>, TP 1 sekalipun
        tidak diizinkan — perlu 100% Pass. Eskalasi prioritas sebelum batch berikutnya
        dijadwalkan untuk ekspor.<br>
        4. <b>Pantau trend pass rate bulanan</b> (chart di atas) untuk lihat apakah ada
        perbaikan setelah tindak lanjut dari Produksi/R&D.
        {anomaly_line}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ══════════════════════════════════════════════════════════════
    # 5. DAMPAK YANG DIHARAPKAN
    # ══════════════════════════════════════════════════════════════
    st.markdown("### 5️⃣ Dampak yang Diharapkan")
    if top_param and top_param_n > 0:
        import math
        potential_pass  = min(n_pass + top_param_n, n_total)
        potential_exact = round(potential_pass / n_total * 100, 1)
        band_lo = 5 * math.floor(potential_exact / 5)
        band_hi = 5 * math.ceil(potential_exact / 5)
        band_text = f"~{band_lo}%" if band_lo == band_hi else f"~{band_lo}–{band_hi}%"

        st.markdown(
            f"""
            <div style="background:#e8f5e9; border-left:4px solid #2E8B57;
                        border-radius:8px; padding:14px 18px; font-size:14px;
                        color:#1a1a1a; line-height:1.85;">
            Kalau masalah parameter <b>{top_param}</b> berhasil diselesaikan (skenario
            optimis — asumsi sampel yang TP <i>hanya</i> karena parameter ini berhasil
            jadi Pass), pass rate <b>{sel_prod}</b> berpotensi naik dari <b>{pass_rate}%</b>
            ke kisaran <b>{band_text}</b>.
            <br><br>
            <span style="font-size:12px; color:#555;">
            Perhitungan: {n_pass} Pass + {top_param_n} sampel TP-karena-{top_param} =
            {potential_pass} dari {n_total} sampel ({potential_exact}%, dibulatkan jadi
            rentang di atas). Ini batas atas skenario optimis, bukan prediksi pasti —
            beberapa sampel mungkin TP di lebih dari satu parameter sekaligus, jadi
            hasil nyata kemungkinan di bawah batas atas ini.
            </span>
            </div>
            """,
            unsafe_allow_html=True,
        )