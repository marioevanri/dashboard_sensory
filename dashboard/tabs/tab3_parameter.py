"""tab3_parameter.py — Parameter & Kualitas Produk."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from config import STATUS_ORDER, STATUS_COLORS, STATUS_NUM, PARAM_COLS, PARAM_LABELS
from insight_engine import (
    gen_insight_parameter, gen_insight_product,
    render_insight_box,
)


# ── Helpers ──────────────────────────────────────────────────────

def _norm_status_label(s: str) -> str:
    """Terjemahkan status ke bahasa yang mudah dipahami."""
    mapping = {
        "Pass":  "✅ Pass (Sesuai standar)",
        "TP 1-": "🟡 Sedikit kurang",
        "TP 1+": "🟡 Sedikit lebih",
        "TP 2-": "🟠 Kurang (perlu evaluasi)",
        "TP 2+": "🟠 Lebih (perlu evaluasi)",
        "TP 3":  "🔴 Off-taste (diblok)",
    }
    return mapping.get(s, s)


def _gap_rate_param(df: pd.DataFrame, param: str) -> dict | None:
    """Hitung gap rate untuk 1 parameter."""
    kc = f"KF_{param}_Status"
    vc = f"V_{param}_Status"
    if kc not in df.columns or vc not in df.columns:
        return None
    both = df[df[kc].notna() & df[vc].notna()]
    if both.empty:
        return None
    total   = len(both)
    mismatch = (both[kc] != both[vc]).sum()
    return {
        "param":    PARAM_LABELS.get(param, param),
        "total":    total,
        "mismatch": int(mismatch),
        "rate":     round(mismatch / total * 100, 1),
    }


# ── Main render ──────────────────────────────────────────────────

def render(df: pd.DataFrame) -> None:
    """Render Tab 3 — Parameter & Kualitas Produk."""
    st.subheader("Parameter & Kualitas Produk")

    # Pengantar storytelling dari Tab 2
    df_mm = df[df["Comparison"] == "MISMATCH"]
    total_mm = len(df_mm)

    # Cari parameter penyebab TP terbanyak
    top_params = []
    for p in PARAM_COLS:
        col = f"KF_{p}_Status"
        if col in df.columns:
            n = (df[col].notna() & (df[col] != "Pass")).sum()
            if n > 0:
                top_params.append((PARAM_LABELS.get(p, p), int(n)))
    top_params.sort(key=lambda x: -x[1])
    top3_text = " · ".join([f"<b>{p}</b> ({n:,} TP)" for p, n in top_params[:3]])

    st.markdown(
        f"""
        <div style="background:#f8f9fa; border-left:4px solid #185FA5;
                    border-radius:8px; padding:14px 18px; margin-bottom:16px;
                    font-size:14px; color:#1a1a1a; line-height:1.8;">
        Di Tab Gap Analysis terlihat <b>{total_mm:,} kejadian gap</b>,
        didominasi <b>Beda Tingkatan</b>.
        &nbsp; Tab ini menjawab dua pertanyaan lanjutan:
        <br>
        🔬 <b>Subtab Gap per Parameter</b> —
        parameter mana yang paling sering menyebabkan perbedaan penilaian?
        &nbsp;·&nbsp;
        📦 <b>Subtab Kualitas per Produk</b> —
        produk mana yang paling sering TP dan apa artinya untuk produksi & R&D?
        <br>
        <span style="font-size:12px; color:#888;">
        Parameter penyebab TP terbanyak: {top3_text}
        </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Internal tabs
    subtab_a, subtab_b = st.tabs([
        "🔬 Gap per Parameter",
        "📦 Kualitas per Produk",
    ])

    with subtab_a:
        _render_gap_per_parameter(df)

    with subtab_b:
        _render_kualitas_per_produk(df)


# ── Subtab A: Gap per Parameter ───────────────────────────────────

def _render_gap_per_parameter(df: pd.DataFrame) -> None:
    """Analisis gap per parameter sensory."""

    st.markdown(
        """
        <div style="font-size:13px; color:#888; margin-bottom:12px;">
        Setiap parameter sensory dinilai secara independen oleh KimFis dan Verifikator.
        Section ini menunjukkan parameter mana yang paling sering berbeda penilaiannya.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Pareto gap per parameter ──────────────────────────────────
    param_stats = []
    for p in PARAM_COLS:
        r = _gap_rate_param(df, p)
        if r:
            param_stats.append(r)

    if not param_stats:
        st.info("Data parameter tidak tersedia.")
        return

    pdf = pd.DataFrame(param_stats).sort_values("rate", ascending=False)

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Gap Rate per Parameter")
        st.caption("% = gap antara KimFis dan Verifikator untuk parameter ini.")
        fig = px.bar(
            pdf, x="rate", y="param", orientation="h",
            text=pdf.apply(
                lambda r: f"{r['rate']}%  ({r['mismatch']} dari {r['total']})", axis=1
            ),
            color="rate",
            color_continuous_scale=["#B5D4F4","#D32F2F"],
            template="plotly_white", height=320,
            labels={"rate":"Gap Rate (%)", "param":"Parameter"},
        )
        fig.update_traces(textposition="outside")
        fig.update_coloraxes(showscale=False)
        fig.update_layout(
            margin=dict(t=10, b=10, l=10, r=80),
            yaxis=dict(categoryorder="total ascending"),
            xaxis=dict(range=[0, pdf["rate"].max() * 1.3]),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("TP Rate per Parameter")
        st.caption("% sampel yang hasilnya TP (bukan Pass) dari Verifikator.")
        tp_stats = []
        for p in PARAM_COLS:
            col = f"V_{p}_Status"
            if col in df.columns:
                total = df[col].notna().sum()
                n_tp  = (df[col].notna() & (df[col] != "Pass")).sum()
                if total > 0:
                    tp_stats.append({
                        "param": PARAM_LABELS.get(p, p),
                        "total": total,
                        "n_tp":  int(n_tp),
                        "rate":  round(n_tp / total * 100, 1),
                    })
        if tp_stats:
            tdf = pd.DataFrame(tp_stats).sort_values("rate", ascending=False)
            fig2 = px.bar(
                tdf, x="rate", y="param", orientation="h",
                text=tdf.apply(
                    lambda r: f"{r['rate']}%  ({r['n_tp']:,} TP)", axis=1
                ),
                color="rate",
                color_continuous_scale=["#B5D4F4","#D32F2F"],
                template="plotly_white", height=320,
                labels={"rate":"TP Rate (%)", "param":"Parameter"},
            )
            fig2.update_traces(textposition="outside")
            fig2.update_coloraxes(showscale=False)
            fig2.update_layout(
                margin=dict(t=10, b=10, l=10, r=80),
                yaxis=dict(categoryorder="total ascending"),
                xaxis=dict(range=[0, tdf["rate"].max() * 1.3]),
            )
            st.plotly_chart(fig2, use_container_width=True)

    # ── Fix 2: Insight box dari engine — threshold relatif ────────────
    if param_stats:
        # Hitung direction per parameter dari data gap
        enriched = []
        for p_stat in param_stats:
            param_key = next(
                (p for p in PARAM_COLS if PARAM_LABELS.get(p, p) == p_stat["param"]), None
            )
            direction = None
            if param_key:
                kc = f"KF_{param_key}_Status"
                vc = f"V_{param_key}_Status"
                if kc in df.columns and vc in df.columns:
                    gaps_df = df[
                        df[kc].notna() & df[vc].notna() & (df[kc] != df[vc])
                    ].copy()
                    if not gaps_df.empty:
                        # Arah dari KimFis ke Verif: KF lebih baik (longgar) atau lebih buruk?
                        gaps_df["KF_N"] = gaps_df[kc].map(STATUS_NUM).fillna(0)
                        gaps_df["VF_N"] = gaps_df[vc].map(STATUS_NUM).fillna(0)
                        gaps_df["Delta"] = gaps_df["KF_N"] - gaps_df["VF_N"]
                        # Delta > 0: KF lebih baik → Verif lebih buruk → produk kurang menurut Verif
                        # Delta < 0: KF lebih buruk → Verif lebih baik → produk lebih menurut Verif
                        mean_delta = gaps_df["Delta"].mean()
                        if mean_delta > 0.2:
                            direction = "kurang"   # KF bilang OK, Verifikator bilang kurang
                        elif mean_delta < -0.2:
                            direction = "lebih"    # KF bilang bermasalah, Verifikator bilang lebih
                        else:
                            direction = "mixed"
            enriched.append({**p_stat, "direction": direction})

        render_insight_box(gen_insight_parameter(enriched), context="parameter")

    st.divider()

    # ── Detail per parameter ──────────────────────────────────────
    st.subheader("Detail per Parameter")
    sel_param = st.selectbox(
        "Pilih parameter untuk lihat detail:",
        [p for p in PARAM_COLS if f"KF_{p}_Status" in df.columns],
        format_func=lambda x: PARAM_LABELS.get(x, x),
        key="param_detail_select",
    )

    kc = f"KF_{sel_param}_Status"
    vc = f"V_{sel_param}_Status"

    if kc in df.columns:
        col_d1, col_d2 = st.columns(2)

        with col_d1:
            st.caption(f"**Distribusi status** — {PARAM_LABELS[sel_param]}")
            # KimFis vs Verifikator side by side — pakai persentase supaya apple-to-apple
            kf_total = df[kc].notna().sum()
            kf_d = (df[kc].value_counts()
                    .rename_axis("Status").reset_index(name="n"))
            kf_d["Persen"] = (kf_d["n"] / kf_total * 100).round(1)
            kf_d["Sumber"] = "KimFis"

            if vc in df.columns:
                vf_total = df[vc].dropna().shape[0]
                vf_d = (df[vc].dropna().value_counts()
                        .rename_axis("Status").reset_index(name="n"))
                vf_d["Persen"] = (vf_d["n"] / vf_total * 100).round(1) if vf_total > 0 else 0
                vf_d["Sumber"] = "Verifikator"
                dist = pd.concat([kf_d, vf_d], ignore_index=True)
            else:
                dist = kf_d

            dist = dist[dist["Status"].isin(STATUS_ORDER)]
            dist["Status"] = pd.Categorical(dist["Status"], STATUS_ORDER, ordered=True)
            fig3 = px.bar(
                dist.sort_values("Status"),
                x="Status", y="Persen", color="Sumber", barmode="group",
                color_discrete_map={"KimFis":"#185FA5","Verifikator":"#EF9F27"},
                category_orders={"Status": STATUS_ORDER},
                text_auto=True, template="plotly_white", height=280,
            )
            fig3.update_layout(
                legend=dict(orientation="h", y=1.1),
                margin=dict(t=20, b=10, l=10, r=10),
                xaxis_title="", yaxis_title="% dari total masing-masing sumber",
            )
            st.plotly_chart(fig3, use_container_width=True)

        with col_d2:
            st.caption(f"**Trend bulanan** — TP Rate {PARAM_LABELS[sel_param]}")
            dft = df.copy()
            dft["Month"] = pd.to_datetime(dft["Date"], errors="coerce").dt.to_period("M").astype(str)
            if vc in dft.columns:
                trend = (
                    dft[dft[vc].notna()]
                    .groupby("Month")
                    .agg(
                        Total=(vc, "count"),
                        TP=(vc, lambda x: (x != "Pass").sum()),
                    )
                    .reset_index()
                )
                trend["TP Rate %"] = (trend["TP"] / trend["Total"] * 100).round(1)

                # Fix 3: sembunyikan trend kalau data terlalu sparse
                max_tp_rate = trend["TP Rate %"].max()
                total_tp    = trend["TP"].sum()

                if max_tp_rate < 0.5 or total_tp < 5:
                    st.markdown(
                        f"<div style='color:#888; font-size:12px; padding:20px 0;'>"
                        f"Parameter ini sangat jarang TP "
                        f"(total {int(total_tp)} kejadian, max {max_tp_rate}% per bulan) "
                        f"— tidak ada pola trend yang signifikan.</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    fig4 = px.line(
                        trend, x="Month", y="TP Rate %",
                        markers=True, template="plotly_white", height=280,
                        labels={"Month":"Bulan", "TP Rate %":"TP Rate (%)"},
                        text="TP Rate %",
                    )
                    fig4.update_traces(
                        textposition="top center",
                        line=dict(color="#D32F2F", width=2),
                        marker=dict(color="#D32F2F", size=7),
                        textfont=dict(size=10),
                    )
                    fig4.update_layout(
                        margin=dict(t=20, b=40, l=10, r=10),
                        xaxis=dict(tickangle=-45),
                        yaxis=dict(range=[0, max(max_tp_rate * 1.3, 5)]),
                    )
                    st.plotly_chart(fig4, use_container_width=True)

        # Top gap type untuk parameter ini
        if vc in df.columns:
            both = df[df[kc].notna() & df[vc].notna()].copy()
            both["Gap_Type"] = both[kc] + " → " + both[vc]
            gaps = both[both[kc] != both[vc]]["Gap_Type"].value_counts().head(5)
            if not gaps.empty:
                st.caption(f"**Top gap type** — {PARAM_LABELS[sel_param]}")
                gdf = gaps.reset_index()
                gdf.columns = ["Gap Type", "Jumlah"]
                gdf["% dari Gap"] = (gdf["Jumlah"] / gaps.sum() * 100).round(1)
                st.dataframe(gdf, use_container_width=True, hide_index=True, height=200)


# ── Subtab B: Kualitas per Produk ─────────────────────────────────

def _render_kualitas_per_produk(df: pd.DataFrame) -> None:
    """Distribusi status per produk — untuk R&D, Produksi, Orang Awam."""

    st.markdown(
        """
        <div style="background:#f0f7ff; border-left:4px solid #2E8B57;
                    border-radius:8px; padding:12px 16px; margin-bottom:16px;
                    font-size:13px; color:#1a1a1a; line-height:1.7;">
        📦 <b>Untuk Produksi & R&D:</b>
        Section ini menunjukkan <b>kualitas aktual produk</b> berdasarkan
        penilaian Verifikator (ground truth) — bukan gap analis.
        Gunakan ini untuk evaluasi formula, proses produksi, dan prioritas perbaikan.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Overview: Top produk berdasarkan TP rate ──────────────────
    st.subheader("Overview Kualitas Produk")

    df_verif = df[df["Verif_Status"].notna()].copy()
    if df_verif.empty:
        st.info("Tidak ada data verifikasi.")
        return

    prod_stats = (
        df_verif.groupby("Product_Name")
        .agg(
            Total=("Verif_Status","count"),
            Pass=("Verif_Status", lambda x: (x=="Pass").sum()),
            TP1=("Verif_Status", lambda x: x.isin(["TP 1-","TP 1+"]).sum()),
            TP2=("Verif_Status", lambda x: x.isin(["TP 2-","TP 2+"]).sum()),
            TP3=("Verif_Status", lambda x: (x=="TP 3").sum()),
        )
        .reset_index()
    )
    prod_stats["Release Ready"] = prod_stats["Pass"] + prod_stats["TP1"]
    prod_stats["Not Pass"]      = prod_stats["TP2"] + prod_stats["TP3"]
    prod_stats["TP Rate %"]     = ((prod_stats["Total"] - prod_stats["Pass"]) / prod_stats["Total"] * 100).round(1)
    prod_stats["Pass Rate %"]   = (prod_stats["Pass"] / prod_stats["Total"] * 100).round(1)
    prod_stats = prod_stats[prod_stats["Total"] >= 10]

    prod_stats["TP Count"] = prod_stats["Total"] - prod_stats["Pass"]
    prod_stats["Score"]    = prod_stats["TP Count"] * (prod_stats["TP Rate %"] / 100)

    # ── Mode selector ─────────────────────────────────────────────
    mode = st.radio(
        "Tampilkan berdasarkan:",
        ["TP Rate (%)", "Jumlah Absolut (TP)", "Composite (Volume × Rate)"],
        horizontal=True,
        key="top10_quality_mode",
    )
    st.caption(
        "**TP Rate %** — bias ke produk trial. &nbsp;"
        "**Jumlah Absolut** — tangkap produk volume tinggi. &nbsp;"
        "**Composite** — gabungan: produk yang sering jalan DAN banyak TP."
    )

    col_ov1, col_ov2 = st.columns(2)

    with col_ov1:
        if mode == "TP Rate (%)":
            chart_df = prod_stats.nlargest(10, "TP Rate %").sort_values("TP Rate %")
            x_col, x_label = "TP Rate %", "TP Rate (%)"
            chart_df["_label"] = chart_df.apply(
                lambda r: f"{r['TP Rate %']}%  ({int(r['TP Count'])} dari {int(r['Total'])})", axis=1)
            cap = "Top 10 — TP Rate tertinggi"
        elif mode == "Jumlah Absolut (TP)":
            chart_df = prod_stats.nlargest(10, "TP Count").sort_values("TP Count")
            x_col, x_label = "TP Count", "Jumlah TP"
            chart_df["_label"] = chart_df.apply(
                lambda r: f"{int(r['TP Count'])}  ({r['TP Rate %']}%)", axis=1)
            cap = "Top 10 — Jumlah TP terbanyak"
        else:
            chart_df = prod_stats.nlargest(10, "Score").sort_values("Score")
            x_col, x_label = "Score", "Composite Score"
            chart_df["_label"] = chart_df.apply(
                lambda r: f"{r['TP Rate %']}%  |  {int(r['TP Count'])} TP", axis=1)
            cap = "Top 10 — Composite Score tertinggi"

        st.caption(f"**{cap}** (Verif — ground truth)")
        fig_tp = px.bar(
            chart_df, x=x_col, y="Product_Name", orientation="h",
            text="_label", color=x_col,
            color_continuous_scale=["#B5D4F4","#D32F2F"],
            template="plotly_white", height=380,
            labels={"Product_Name":"Produk", x_col:x_label},
        )
        fig_tp.update_traces(textposition="outside")
        fig_tp.update_coloraxes(showscale=False)
        fig_tp.update_layout(
            margin=dict(t=10, b=10, l=10, r=120),
            xaxis=dict(range=[0, chart_df[x_col].max() * 1.5]),
        )
        st.plotly_chart(fig_tp, use_container_width=True)

    with col_ov2:
        st.caption("**Top 10 produk — Pass Rate terendah** (produk yang paling jarang Pass)")
        bot_pass = prod_stats.nsmallest(10, "Pass Rate %").sort_values("Pass Rate %", ascending=False)
        colors   = ["#D32F2F" if r < 50 else "#E65100" if r < 70 else "#185FA5"
                    for r in bot_pass["Pass Rate %"]]
        fig_pass = go.Figure(go.Bar(
            x=bot_pass["Pass Rate %"],
            y=bot_pass["Product_Name"],
            orientation="h",
            text=bot_pass["Pass Rate %"].apply(lambda x: f"{x}%"),
            textposition="outside",
            marker_color=colors,
        ))
        fig_pass.update_layout(
            template="plotly_white", height=380,
            margin=dict(t=10, b=10, l=10, r=60),
            xaxis=dict(title="Pass Rate (%)", range=[0, 110]),
            yaxis=dict(title=""),
        )
        st.plotly_chart(fig_pass, use_container_width=True)

    st.divider()

    # ── Drill-down per produk ─────────────────────────────────────
    st.subheader("Drill-down Kualitas per Produk")
    st.caption("Pilih produk untuk lihat distribusi status, trend, dan parameter penyebab TP.")

    all_prods = sorted(prod_stats["Product_Name"].unique())
    sel_prod  = st.selectbox(
        "Pilih produk:",
        ["— Pilih produk —"] + all_prods,
        key="prod_quality_select",
    )

    if sel_prod == "— Pilih produk —":
        return

    prod_df   = df_verif[df_verif["Product_Name"] == sel_prod].copy()
    prod_all  = df[df["Product_Name"] == sel_prod].copy()
    total_p   = len(prod_df)
    n_pass    = (prod_df["Verif_Status"] == "Pass").sum()
    n_tp1     = prod_df["Verif_Status"].isin(["TP 1-","TP 1+"]).sum()
    n_tp2     = prod_df["Verif_Status"].isin(["TP 2-","TP 2+"]).sum()
    n_tp3     = (prod_df["Verif_Status"] == "TP 3").sum()
    n_release = n_pass + n_tp1
    n_notpass = n_tp2 + n_tp3
    tp_rate   = round((total_p - n_pass) / total_p * 100, 1) if total_p else 0
    pass_rate = round(n_pass / total_p * 100, 1) if total_p else 0

    # ── Insight otomatis ──────────────────────────────────────────
    n_tp_all  = n_tp1 + n_tp2 + n_tp3
    all_tp1   = (n_tp2 == 0 and n_tp3 == 0 and n_tp1 > 0)

    if tp_rate >= 80:
        insight_color = "#D32F2F"
        insight_icon  = "🔴"
        if all_tp1:
            insight_text = (
                f"Produk ini sangat jarang Pass — {pass_rate}% dari {total_p} sampel. "
                f"Semua TP adalah TP 1 (masih release), tapi berada di batas bawah standar. "
                f"Risiko tinggi complaint — perlu evaluasi formula segera."
            )
        else:
            insight_text = (
                f"Produk ini sangat jarang Pass — hanya {pass_rate}% dari {total_p} sampel. "
                f"Perlu evaluasi formula atau proses produksi segera."
            )
    elif tp_rate >= 50:
        insight_color = "#E65100"
        insight_icon  = "🟠"
        if all_tp1:
            insight_text = (
                f"Lebih dari separuh sampel ({tp_rate}%) menghasilkan TP 1 — masih bisa release, "
                f"tapi produk ini konsisten berada di batas bawah standar. "
                f"Perlu investigasi parameter untuk mencegah potensi complaint di masa depan."
            )
        else:
            insight_text = (
                f"Lebih dari separuh sampel ({tp_rate}%) menghasilkan TP. "
                f"Perlu investigasi parameter yang paling sering menyimpang."
            )
    elif tp_rate >= 20:
        insight_color = "#185FA5"
        insight_icon  = "🟡"
        insight_text  = (
            f"Pass rate {pass_rate}% — masih ada ruang perbaikan. "
            f"Perhatikan parameter dengan TP terbanyak di bawah."
        )
    else:
        insight_color = "#2E8B57"
        insight_icon  = "🟢"
        insight_text  = (
            f"Pass rate {pass_rate}% — kualitas produk ini cukup baik. "
            f"Pertahankan konsistensi proses produksi."
        )

    st.markdown(
        f"""
        <div style="background:#f8f9fa; border-left:4px solid {insight_color};
                    border-radius:8px; padding:12px 16px; margin-bottom:12px;
                    font-size:14px; color:#1a1a1a; line-height:1.8;">
        {insight_icon} <b>{sel_prod}</b> — {insight_text}
        <br>
        <span style="font-size:12px; color:#666;">
        Dari {total_p} sampel terverifikasi:
        &nbsp; <b style="color:#2E8B57">{n_pass} Pass ({pass_rate}%)</b>
        &nbsp;·&nbsp; <b style="color:#D85A30">{n_tp1} TP 1</b>
        &nbsp;·&nbsp; <b style="color:#8B0000">{n_tp2} TP 2</b>
        &nbsp;·&nbsp; <b style="color:#0D0D5C">{n_tp3} TP 3</b>
        &nbsp;·&nbsp; Release ready: <b style="color:#2E8B57">{n_release} ({round(n_release/total_p*100,1)}%)</b>
        &nbsp;·&nbsp; Not Pass: <b style="color:#D32F2F">{n_notpass} ({round(n_notpass/total_p*100,1)}%)</b>
        </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_p1, col_p2 = st.columns(2)

    # Distribusi status
    with col_p1:
        st.caption("**Distribusi status** (Verif — ground truth)")
        vd = (prod_df["Verif_Status"].value_counts()
              .reindex(STATUS_ORDER).dropna().reset_index())
        vd.columns = ["Status","Jumlah"]
        vd["Pct"] = (vd["Jumlah"] / total_p * 100).round(1)
        vd["Label"] = vd.apply(lambda r: f"{r['Pct']}%", axis=1)
        fig_s = px.bar(
            vd, x="Status", y="Jumlah", text="Label",
            color="Status", color_discrete_map=STATUS_COLORS,
            category_orders={"Status": STATUS_ORDER},
            template="plotly_white", height=250,
        )
        fig_s.update_traces(textposition="outside")
        fig_s.update_layout(
            showlegend=False,
            margin=dict(t=10,b=10,l=10,r=10),
            xaxis_title="", yaxis_title="",
        )
        st.plotly_chart(fig_s, use_container_width=True)

    # Trend Pass Rate bulanan
    with col_p2:
        st.caption("**Trend Pass Rate bulanan**")
        prod_df["Month"] = pd.to_datetime(prod_df["Date"], errors="coerce").dt.to_period("M").astype(str)
        trend_p = (
            prod_df.groupby("Month")
            .agg(
                Total=("Verif_Status","count"),
                Pass=("Verif_Status", lambda x: (x=="Pass").sum()),
            )
            .reset_index()
        )
        trend_p["Pass Rate %"] = (trend_p["Pass"] / trend_p["Total"] * 100).round(1)
        fig_tr = px.line(
            trend_p, x="Month", y="Pass Rate %",
            markers=True, template="plotly_white", height=250,
            text="Pass Rate %",
        )
        fig_tr.update_traces(
            textposition="top center",
            line=dict(color="#2E8B57", width=2),
            marker=dict(color="#2E8B57", size=7),
            textfont=dict(size=10),
        )
        fig_tr.add_hline(
            y=100, line_dash="dot", line_color="#D32F2F",
            annotation_text="Target 100%",
            annotation_position="bottom right",
        )
        fig_tr.update_layout(
            margin=dict(t=10,b=40,l=10,r=10),
            xaxis=dict(tickangle=-45),
            yaxis=dict(range=[0, 110]),
        )
        st.plotly_chart(fig_tr, use_container_width=True)

    # Top parameter TP — dari Verifikator (konsisten dengan distribusi status di atas)
    st.caption("**Parameter penyebab TP** (dari Verifikator)")
    param_tp = []
    for p in PARAM_COLS:
        col_p = f"V_{p}_Status"
        if col_p in prod_all.columns:
            n_tp = (prod_all[col_p].notna() & (prod_all[col_p] != "Pass")).sum()
            if n_tp > 0:
                tp_vals = prod_all[prod_all[col_p].notna() & (prod_all[col_p] != "Pass")][col_p]
                n_minus = tp_vals.str.endswith("-").sum()
                n_plus  = tp_vals.str.endswith("+").sum()
                if n_minus > n_plus:
                    arah = "↓ kurang dari standar"
                elif n_plus > n_minus:
                    arah = "↑ lebih dari standar"
                else:
                    arah = "↕ bervariasi"
                param_tp.append({
                    "Parameter":    PARAM_LABELS.get(p, p),
                    "Jumlah TP":    int(n_tp),
                    "% dari total": round(n_tp / len(prod_all) * 100, 1),
                    "Arah dominan": arah,
                })
    if param_tp:
        ptdf = pd.DataFrame(param_tp).sort_values("Jumlah TP", ascending=False).reset_index(drop=True)
        ptdf.index += 1
        st.dataframe(ptdf, use_container_width=True, hide_index=False, height=230)

        # Insight box per produk dari engine
        top_row  = ptdf.iloc[0]
        top_param_name = top_row["Parameter"]
        arah_str = top_row["Arah dominan"]
        if "kurang" in arah_str:
            top_dir = "kurang"
        elif "lebih" in arah_str:
            top_dir = "lebih"
        else:
            top_dir = "mixed"

        render_insight_box(
            gen_insight_product(
                prod_name    = sel_prod,
                tp_rate      = tp_rate,
                pass_rate    = pass_rate,
                n_total      = total_p,
                top_param    = top_param_name,
                top_direction= top_dir,
            ),
            context="product_drilldown"
        )
    else:
        st.info("Tidak ada data parameter TP.")

    # Navigasi ke tab berikutnya
    st.markdown(
        """
        <div style="font-size:12px; color:#666; margin-top:8px; line-height:1.8;">
        💡 <b>Lanjutkan investigasi:</b>
        &nbsp; 🏭 <b>Tab Shift & Analis</b> — siapa analis yang paling sering beda
        penilaiannya untuk produk ini?
        &nbsp;·&nbsp; 📋 <b>Tab Daily Report</b> — lihat detail per batch untuk
        keputusan release.
        </div>
        """,
        unsafe_allow_html=True,
    )