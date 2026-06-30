"""tab1_overview.py — Overview KPI dan distribusi status."""

import pandas as pd
import plotly.express as px
import streamlit as st
from config import STATUS_ORDER, STATUS_COLORS, PARAM_COLS, PARAM_LABELS


def _get_top_params(df: pd.DataFrame, top_n: int = 3, min_tp: int = 100) -> list:
    """
    Parameter yang paling sering menyebabkan TP (dari KF_Status per param).
    min_tp: minimum jumlah TP supaya tidak bias oleh parameter yang jarang muncul.
    """
    counts = {}
    for p in PARAM_COLS:
        col = f"KF_{p}_Status"
        if col in df.columns:
            n_tp = (df[col].notna() & (df[col] != "Pass")).sum()
            if n_tp >= min_tp:
                counts[PARAM_LABELS.get(p, p)] = int(n_tp)

    # Kalau tidak ada yang memenuhi threshold, turunkan threshold
    if not counts:
        for p in PARAM_COLS:
            col = f"KF_{p}_Status"
            if col in df.columns:
                n_tp = (df[col].notna() & (df[col] != "Pass")).sum()
                if n_tp > 0:
                    counts[PARAM_LABELS.get(p, p)] = int(n_tp)

    return sorted(counts.items(), key=lambda x: -x[1])[:top_n]


def _status_counts(df: pd.DataFrame) -> dict:
    """
    Hitung distribusi status:
    - Distribusi kualitas: HANYA dari Verif_Status (ground truth)
    - Sampel tidak diverifikasi TIDAK ikut dihitung distribusi kualitas
    - n_kf_only: jumlah sampel yang tidak diverifikasi (info transparansi)
    """
    total     = len(df)
    n_verif   = df["Verif_Status"].notna().sum()
    n_kf_only = total - n_verif

    # Distribusi kualitas hanya dari sampel yang terverifikasi
    verif_only = df[df["Verif_Status"].notna()]["Verif_Status"]
    n_pass    = (verif_only == "Pass").sum()
    n_tp1     = verif_only.isin(["TP 1-","TP 1+"]).sum()
    n_tp2     = verif_only.isin(["TP 2-","TP 2+"]).sum()
    n_tp3     = (verif_only == "TP 3").sum()
    n_release = n_pass + n_tp1
    n_notpass = n_tp2 + n_tp3

    def pct(n): return n / n_verif * 100 if n_verif else 0

    return dict(
        total=total, n_verif=n_verif, n_kf_only=n_kf_only,
        n_pass=n_pass, n_tp1=n_tp1, n_tp2=n_tp2, n_tp3=n_tp3,
        n_release=n_release, n_notpass=n_notpass,
        pct_pass=pct(n_pass), pct_tp1=pct(n_tp1),
        pct_tp2=pct(n_tp2), pct_tp3=pct(n_tp3),
        pct_release=pct(n_release), pct_notpass=pct(n_notpass),
    )


def _trend_text(df: pd.DataFrame) -> str:
    """
    Tampilkan trend gap sesuai konteks filter:
    - Filter 1 bulan saja → MoM (vs bulan sebelumnya dari df_all)
    - Filter lebih dari 1 bulan → tidak tampilkan trend (misleading)
      → tampilkan baseline KPI saja
    Untuk perbandingan YoY/QoQ → butuh data periode lengkap,
    akan diaktifkan saat data 2024 tersedia.
    """
    try:
        df2 = df.copy()
        df2["Date_dt"] = pd.to_datetime(df2["Date"], errors="coerce")
        df2["YM"] = df2["Date_dt"].dt.to_period("M")
        months = sorted(df2["YM"].dropna().unique())

        # Hanya tampilkan MoM kalau filter = 1 bulan saja
        if len(months) != 1:
            return ""

        # Ambil bulan filter dan bulan sebelumnya
        cur_m  = months[0]
        prev_m = cur_m - 1

        def gap_rate_period(period):
            sub = df2[df2["YM"] == period]
            vf  = sub["Verif_Status"].notna().sum()
            mm  = (sub["Comparison"] == "MISMATCH").sum()
            return mm / vf * 100 if vf >= 10 else None

        cur_rate  = gap_rate_period(cur_m)
        prev_rate = gap_rate_period(prev_m)

        if cur_rate is None or prev_rate is None:
            return ""

        diff = cur_rate - prev_rate
        if abs(diff) < 0.5:
            return (
                f"&nbsp;<span style='color:#888;font-weight:500'>"
                f"→ stabil vs {str(prev_m)}</span>"
            )
        arrow = "↑" if diff > 0 else "↓"
        color = "#D32F2F" if diff > 0 else "#2E8B57"
        label = "gap meningkat ⚠️" if diff > 0 else "gap menurun ✅"
        return (
            f"&nbsp;<span style='color:{color};font-weight:600'>"
            f"{arrow} {abs(diff):.1f}% vs {str(prev_m)} — {label}</span>"
        )
    except Exception:
        return ""


def _executive_summary(df: pd.DataFrame) -> None:
    """Auto-generate Executive Summary dari data."""
    if df.empty:
        return

    sc        = _status_counts(df)
    total     = sc["total"]
    n_verif   = sc["n_verif"]
    n_kf_only = sc["n_kf_only"]

    # Gap KimFis vs Verif
    mismatch  = (df["Comparison"] == "MISMATCH").sum()
    gap_rate  = mismatch / n_verif * 100 if n_verif else 0

    # Trend Month-over-Month
    mom_text = _trend_text(df)

    # Produk dengan composite score tertinggi (min 20 sampel)
    prod_df = (
        df[df["Comparison"].isin(["MATCH","MISMATCH"])]
        .groupby("Product_Name")
        .agg(Total=("Comparison","count"),
             Mismatch=("Comparison", lambda x: (x=="MISMATCH").sum()))
        .reset_index()
    )
    prod_df = prod_df[prod_df["Total"] >= 20]
    if not prod_df.empty:
        prod_df["Rate"]  = prod_df["Mismatch"] / prod_df["Total"] * 100
        prod_df["Score"] = prod_df["Mismatch"] * (prod_df["Rate"] / 100)
        wp = prod_df.nlargest(1,"Score").iloc[0]
        prod_text = (
            f"<b>{wp['Product_Name']}</b> — "
            f"<b style='color:#D32F2F'>{wp['Rate']:.1f}%</b> gap rate "
            f"({int(wp['Mismatch'])} dari {int(wp['Total'])} sampel)"
        )
    else:
        prod_text = "Data tidak cukup (min. 20 sampel)"

    # Shift dengan gap rate tertinggi
    def norm_shift(v):
        s = str(v).strip()
        try:
            f = float(s)
            if f == int(f): return str(int(f))
        except: pass
        return s

    df2 = df.copy()
    df2["Shift_Label"] = df2["Shift_Code"].apply(norm_shift)
    sh_df = (
        df2[df2["Comparison"].isin(["MATCH","MISMATCH"])]
        .groupby("Shift_Label")
        .agg(Total=("Comparison","count"),
             Mismatch=("Comparison", lambda x: (x=="MISMATCH").sum()))
        .reset_index()
    )
    sh_df = sh_df[sh_df["Total"] >= 20]
    if not sh_df.empty:
        sh_df["Rate"] = sh_df["Mismatch"] / sh_df["Total"] * 100
        ws = sh_df.nlargest(1,"Rate").iloc[0]
        shift_text = (
            f"Shift <b>{ws['Shift_Label']}</b> — "
            f"<b style='color:#D32F2F'>{ws['Rate']:.1f}%</b> gap rate "
            f"dari {int(ws['Total'])} sampel terverifikasi"
        )
    else:
        shift_text = "Data tidak cukup"

    # Top parameter — min 100 TP, fallback ke threshold lebih rendah
    top_params = _get_top_params(df, top_n=3, min_tp=100)
    if top_params:
        total_tp = sum(n for _, n in top_params)
        param_text = " &nbsp;·&nbsp; ".join(
            [f"<b>{p}</b> ({n:,} TP)" for p, n in top_params]
        )
    else:
        param_text = "Data parameter tidak tersedia"

    # ── Render Box 1: Kualitas Produksi ──────────────────────────
    st.markdown("### 📋 Executive Summary")
    st.markdown(
        f"""
        <div style="background:#f8f9fa; border-left:4px solid #185FA5;
                    border-radius:8px; padding:16px 20px; margin-bottom:8px;
                    line-height:2.1; font-size:14px; color:#1a1a1a;">

        <div style="font-size:11px; color:#888; margin-bottom:8px;">
            📌 Status menggunakan <b>Verifikator</b> sebagai ground truth
            (<b>{n_verif:,}</b> sampel dikonfirmasi Verifikator).
            <b>{n_kf_only:,}</b> sampel tidak diverifikasi → digunakan hasil
            <b>KimFis</b> sebagai estimasi.
            Sebagian sampel memang tidak diverifikasi — verifikasi dilakukan secara sampling.
            &nbsp;|&nbsp;
            <b>KimFis</b> = konsensus majority vote dari <b>3 analis</b> per mix/IBC (analis shift di laboratorium Kimia Fisika).
            <b>Verifikator</b> = penilaian akhir dari QC Verifikator (1 orang, ground truth).
        </div>

        <div>
            🏭 <b>Distribusi kualitas ({n_verif:,} sampel terverifikasi — ground truth Verif):</b>
            &nbsp;
            <b style="color:#2E8B57">{sc['pct_pass']:.1f}% Pass
            ({sc['n_pass']:,})</b>
            &nbsp;·&nbsp;
            <b style="color:#D85A30">{sc['pct_tp1']:.1f}% TP 1
            ({sc['n_tp1']:,})</b>
            &nbsp;·&nbsp;
            <b style="color:#8B0000">{sc['pct_tp2']:.1f}% TP 2
            ({sc['n_tp2']:,})</b>
            &nbsp;·&nbsp;
            <b style="color:#0D0D5C">{sc['pct_tp3']:.1f}% TP 3
            ({sc['n_tp3']:,})</b>
        </div>

        <div style="margin-top:4px;">
            ✅ <b>Release ready</b> (Pass + TP 1):
            <b style="color:#2E8B57">
            {sc['pct_release']:.1f}% ({sc['n_release']:,} sampel)</b>
            &nbsp;&nbsp;
            ❌ <b>Not Pass</b> (TP 2 + TP 3):
            <b style="color:#8B0000">
            {sc['pct_notpass']:.1f}% ({sc['n_notpass']:,} sampel)</b>
        </div>

        <div style="margin-top:4px; font-size:12px; color:#666;">
            TP 1 masih bisa release &nbsp;·&nbsp;
            TP 2 perlu tinjauan &amp; Triangle Test &nbsp;·&nbsp;
            TP 3 diblok &nbsp;·&nbsp;
            <b>Preshipment/eksport: wajib 100% Pass</b>
        </div>

        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Render Box 2: Gap KimFis vs Verifikator ────────────────────────
    st.markdown(
        f"""
        <div style="background:#f8f9fa; border-left:4px solid #D32F2F;
                    border-radius:8px; padding:16px 20px; margin-bottom:8px;
                    line-height:2.1; font-size:14px; color:#1a1a1a;">

        <div>
            📊 <b>Gap KimFis vs Verifikator</b>
            ({n_verif:,} sampel terverifikasi):
            <b style="color:#D32F2F">{gap_rate:.1f}% gap rate
            ({mismatch:,} kejadian)</b>{mom_text}
        </div>

        <div style="margin-top:2px; font-size:12px; color:#888;">
            💡 Gap = perbedaan penilaian antara KimFis dan Verifikator.
            Setiap gap perlu ditelusuri karena dapat berdampak pada
            akurasi keputusan release — terutama untuk
            <b>produk preshipment/eksport yang wajib 100% approval</b>
            dan untuk mencegah potensi <b>komplain dari customer</b>.
        </div>

        <div style="
            margin-top:10px;
            background: linear-gradient(135deg, #fff3e0, #fce4ec);
            border: 1.5px solid #E65100;
            border-radius: 6px;
            padding: 10px 14px;
            font-size: 13px;
            color: #1a1a1a;
            line-height: 1.8;
        ">
            🎯 <b>Baseline KPI Sensory</b>
            &nbsp;—&nbsp;
            acuan untuk semua periode:
            &nbsp;&nbsp;
            <span style="
                background:#D32F2F; color:white;
                padding:2px 10px; border-radius:100px;
                font-weight:600; font-size:12px;
            ">0 complaint dari customer</span>
            &nbsp;&nbsp;
            <span style="
                background:#1565C0; color:white;
                padding:2px 10px; border-radius:100px;
                font-weight:600; font-size:12px;
            ">100% approval preshipment/eksport</span>
        </div>

        <div style="margin-top:6px;">
            ⚠️ <b>Produk dengan gap tertinggi:</b> {prod_text}
        </div>

        <div style="margin-top:4px;">
            🕐 <b>Shift dengan gap tertinggi:</b> {shift_text}
        </div>

        <div style="margin-top:4px;">
            🔬 <b>Parameter penyebab TP terbanyak:</b> {param_text}
        </div>

        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Navigation hints ──────────────────────────────────────────
    st.markdown(
        """
        <div style="font-size:12px; color:#666; margin-top:4px;
                    line-height:2; padding:6px 4px;">
        💡 <b>Lanjutkan investigasi:</b>
        &nbsp;📈 <b>Gap Analysis</b> — tipe gap apa yang dominan &amp; trennya
        &nbsp;·&nbsp; 🔬 <b>Parameter</b> — parameter mana yang paling sering TP
        &nbsp;·&nbsp; 🏭 <b>Shift &amp; Analis</b> — siapa dan kapan paling banyak gap
        &nbsp;·&nbsp; 📋 <b>Daily Report</b> — detail per batch untuk keputusan release
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("ℹ️ Keterangan lengkap skala status & business rules"):
        st.markdown("""
**Skala penilaian sensory:**

| Status | Arti | Keputusan |
|---|---|---|
| **Pass** | Semua parameter sesuai standar | ✅ Release |
| **TP 1− / TP 1+** | Sedikit di bawah / di atas standar | ⚠️ Release, dengan catatan |
| **TP 2− / TP 2+** | Menyimpang dari standar | 🔶 Tahan — perlu Triangle Test |
| **TP 3** | Off-taste | ❌ Blok |

**Business rules:**
- **KPI Complaint = 0** — tidak boleh ada komplain sensory dari customer
- **Preshipment/Eksport = 100% Pass** — TP 1 tidak diizinkan
- **Gap KimFis vs Verif** — setiap perbedaan penilaian perlu ditelusuri untuk memastikan akurasi keputusan release

**Tentang data di dashboard ini:**
- **Verifikator** = penilaian akhir / ground truth
- **KimFis** = konsensus majority vote 3 analis
- Verifikasi dilakukan secara sampling — tidak semua mix/IBC diverifikasi
- Mix/IBC yang tidak diverifikasi menggunakan hasil KimFis sebagai estimasi
        """)

    st.divider()


def render(df: pd.DataFrame) -> None:
    """Render Tab 1 — Overview."""
    st.subheader("Overview")

    _executive_summary(df)

    # ── KPI Cards ─────────────────────────────────────────────────
    total      = len(df)
    verif      = df["Verif_Status"].notna().sum()
    match      = (df["Comparison"] == "MATCH").sum()
    mismatch   = (df["Comparison"] == "MISMATCH").sum()
    coverage   = verif    / total  * 100 if total else 0
    match_rate = match    / verif  * 100 if verif else 0
    miss_rate  = mismatch / verif  * 100 if verif else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Sampel",   f"{total:,}")
    c2.metric("Terverifikasi",  f"{verif:,}",     f"coverage: {coverage:.1f}%")
    c3.metric("Match",          f"{match:,}",     f"{match_rate:.1f}% dari terverif")
    c4.metric("Gap (Mismatch)", f"{mismatch:,}",  f"{miss_rate:.1f}% dari terverif",
              delta_color="inverse")

    st.divider()
    col_a, col_b = st.columns(2)

    # ── Distribusi Status ──────────────────────────────────────────
    with col_a:
        st.subheader("Distribusi Status")
        st.caption(
            "Verifikator = ground truth (penilaian akhir yang dijadikan acuan). "
            "KimFis = konsensus 3 analis. "
            "Jumlah berbeda karena tidak semua sampel diverifikasi."
        )
        kf_dist = (df["KF_Status"].value_counts()
                   .rename_axis("Status").reset_index(name="Jumlah"))
        kf_dist["Sumber"] = "KimFis"
        vf_dist = (df["Verif_Status"].dropna().value_counts()
                   .rename_axis("Status").reset_index(name="Jumlah"))
        vf_dist["Sumber"] = "Verifikator"

        dist_df = pd.concat([kf_dist, vf_dist], ignore_index=True)
        dist_df = dist_df[dist_df["Status"].isin(STATUS_ORDER)]
        dist_df["Status"] = pd.Categorical(
            dist_df["Status"], STATUS_ORDER, ordered=True
        )
        fig = px.bar(
            dist_df.sort_values("Status"),
            x="Status", y="Jumlah", color="Sumber", barmode="group",
            color_discrete_map={"KimFis":"#185FA5","Verifikator":"#EF9F27"},
            category_orders={"Status": STATUS_ORDER},
            text_auto=True, template="plotly_white", height=380,
        )
        fig.update_layout(
            legend=dict(orientation="h", y=1.1),
            margin=dict(t=30, b=20, l=10, r=10),
            xaxis_title="", yaxis_title="Jumlah Sampel",
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── Top 10 Produk ──────────────────────────────────────────────
    with col_b:
        st.subheader("Top 10 Produk — Gap Tertinggi")
        mode = st.radio(
            "Tampilkan berdasarkan:",
            ["Persentase (%)", "Jumlah Absolut", "Composite (Volume × Rate)"],
            horizontal=True, key="top10_mode",
        )

        top_df = (
            df[df["Comparison"].isin(["MATCH","MISMATCH"])]
            .groupby("Product_Name")
            .agg(Total=("Comparison","count"),
                 Mismatch=("Comparison", lambda x: (x=="MISMATCH").sum()),
                 Match=("Comparison",    lambda x: (x=="MATCH").sum()))
            .reset_index()
        )
        top_df["Rate %"]  = (top_df["Mismatch"] / top_df["Total"] * 100).round(1)
        top_df["Match %"] = (top_df["Match"]    / top_df["Total"] * 100).round(1)
        top_df = top_df[top_df["Total"] >= 20]
        top_df["Score"]   = top_df["Mismatch"] * (top_df["Rate %"] / 100)

        if mode == "Persentase (%)":
            top_df = top_df.nlargest(10,"Rate %").sort_values("Rate %",ascending=False)
            y_col, y_label, color_col = "Rate %", "Gap Rate (%)", "Rate %"
            top_df["Label"] = top_df.apply(
                lambda r: f"{r['Rate %']}%  ({r['Mismatch']} dari {r['Total']})", axis=1)
        elif mode == "Jumlah Absolut":
            top_df = top_df.nlargest(10,"Mismatch").sort_values("Mismatch",ascending=False)
            y_col, y_label, color_col = "Mismatch", "Jumlah Gap", "Mismatch"
            top_df["Label"] = top_df.apply(
                lambda r: f"{r['Mismatch']}  ({r['Rate %']}%)", axis=1)
        else:
            top_df = top_df.nlargest(10,"Score").sort_values("Score",ascending=False)
            y_col, y_label, color_col = "Score", "Composite Score", "Score"
            top_df["Label"] = top_df.apply(
                lambda r: f"{r['Rate %']}%  |  {r['Mismatch']} gap", axis=1)

        fig2 = px.bar(
            top_df, x="Product_Name", y=y_col,
            text="Label", color=color_col,
            color_continuous_scale=["#B5D4F4","#D32F2F"],
            template="plotly_white", height=380,
            labels={"Product_Name":"Produk", y_col:y_label},
            custom_data=["Product_Name","Rate %","Mismatch","Total"],
        )
        fig2.update_traces(
            textposition="outside",
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Gap Rate: %{customdata[1]}%<br>"
                "Gap: %{customdata[2]}<br>"
                "Total: %{customdata[3]}<extra></extra>"
            )
        )
        fig2.update_coloraxes(showscale=False)
        fig2.update_layout(
            xaxis=dict(categoryorder="total descending", tickangle=-45,
                       tickfont=dict(size=10)),
            margin=dict(t=30, b=80, l=10, r=10),
            xaxis_title="", yaxis_title=y_label,
        )
        st.plotly_chart(fig2, use_container_width=True)

        # ── Drill-down produk ──────────────────────────────────────
        if not top_df.empty:
            sel_prod = st.selectbox(
                "🔍 Drill-down produk:",
                ["— Pilih produk —"] + top_df["Product_Name"].tolist(),
                key="drilldown_prod",
            )
            if sel_prod != "— Pilih produk —":
                prod_data = df[df["Product_Name"] == sel_prod]
                verif_prod = prod_data[prod_data["Verif_Status"].notna()]

                dd1, dd2 = st.columns(2)
                with dd1:
                    st.caption(f"**Distribusi status** — {sel_prod}")
                    if not verif_prod.empty:
                        vd = (verif_prod["Verif_Status"].value_counts()
                              .reindex(STATUS_ORDER).dropna()
                              .reset_index())
                        vd.columns = ["Status","Jumlah"]
                        vd["Pct"] = (vd["Jumlah"]/len(verif_prod)*100).round(1)
                        vd["Label"] = vd.apply(
                            lambda r: f"{r['Pct']}% ({r['Jumlah']})", axis=1)
                        fig_dd = px.bar(
                            vd, x="Status", y="Jumlah",
                            text="Label", color="Status",
                            color_discrete_map=STATUS_COLORS,
                            category_orders={"Status": STATUS_ORDER},
                            template="plotly_white", height=220,
                        )
                        fig_dd.update_traces(textposition="outside")
                        fig_dd.update_layout(
                            showlegend=False,
                            margin=dict(t=10,b=10,l=10,r=10),
                            xaxis_title="", yaxis_title="",
                        )
                        st.plotly_chart(fig_dd, use_container_width=True)

                with dd2:
                    st.caption(f"**Top parameter TP** — {sel_prod}")
                    param_rows = []
                    for p in PARAM_COLS:
                        col = f"KF_{p}_Status"
                        if col in prod_data.columns:
                            n_tp = (prod_data[col].notna() &
                                    (prod_data[col] != "Pass")).sum()
                            if n_tp > 0:
                                param_rows.append({
                                    "Parameter": PARAM_LABELS.get(p,p),
                                    "Jumlah TP": int(n_tp),
                                    "Rate %": round(n_tp/len(prod_data)*100,1),
                                })
                    if param_rows:
                        pdf = pd.DataFrame(param_rows).sort_values(
                            "Jumlah TP", ascending=False
                        ).reset_index(drop=True)
                        pdf.index += 1
                        st.dataframe(pdf, use_container_width=True,
                                     hide_index=False, height=200)
                    else:
                        st.info("Tidak ada data parameter TP untuk produk ini.")

    st.divider()
