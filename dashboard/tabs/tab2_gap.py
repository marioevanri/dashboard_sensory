"""tab2_gap.py — Gap Analysis KimFis vs Verifikator."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from config import STATUS_ORDER, STATUS_COLORS, STATUS_NUM
from insight_engine import (
    gen_insight_gap_type, gen_insight_trend,
    render_insight_box,
)


def classify_gap(kf: str, vf: str) -> str | None:
    """
    Klasifikasi gap berdasarkan MAKNA.
    Kategori:
        "Melibatkan TP 3"  — salah satu TP 3 (off-taste)
        "Beda Arah"        — keduanya signed, berlawanan tanda (TP 1- vs TP 1+)
        "Gap Signifikan"   — Pass ke TP 2 apapun arahnya (lompat 2 level via Pass)
                             atau TP 1 ke TP 2 berlawanan arah
        "Beda Tingkatan"   — selisih 1 level, arah sama (Pass→TP1, TP1→TP2)
    Returns None jika match atau status tidak dikenal.
    """
    if kf not in STATUS_NUM or vf not in STATUS_NUM or kf == vf:
        return None
    signed = {"TP 2-", "TP 1-", "TP 1+", "TP 2+"}
    tp2    = {"TP 2-", "TP 2+"}

    if kf == "TP 3" or vf == "TP 3":
        return "Melibatkan TP 3"

    # Beda Arah: dua-duanya signed dan berlawanan tanda
    if kf in signed and vf in signed and STATUS_NUM[kf] * STATUS_NUM[vf] < 0:
        return "Beda Arah"

    # Gap Signifikan: Pass ke TP 2 apapun arahnya (delta = 2, lompati TP 1)
    if (kf == "Pass" and vf in tp2) or (vf == "Pass" and kf in tp2):
        return "Gap Signifikan"

    # Beda Tingkatan: selisih 1 level (termasuk Pass→TP1, TP1→TP2 searah)
    delta = abs(STATUS_NUM[kf] - STATUS_NUM[vf])
    if delta == 1:
        return "Beda Tingkatan"

    # Fallback: selisih besar lainnya yang belum tertangkap
    return "Gap Signifikan"


CAT_ORDER = ["Beda Tingkatan", "Gap Signifikan", "Beda Arah", "Melibatkan TP 3"]
CAT_ICONS = {
    "Beda Tingkatan":  "🟡",
    "Gap Signifikan":  "🟠",
    "Beda Arah":       "🔄",
    "Melibatkan TP 3": "🔴",
}
CAT_COLORS = {
    "Beda Tingkatan":  "#EF9F27",
    "Gap Signifikan":  "#E65100",
    "Beda Arah":       "#185FA5",
    "Melibatkan TP 3": "#D32F2F",
}
CAT_DESC = {
    "Beda Tingkatan":  "Selisih 1 level, arah sama — Pass→TP 1, TP 1→TP 2",
    "Gap Signifikan":  "Pass langsung ke TP 2 (lompati TP 1) atau selisih 2+ level",
    "Beda Arah":       "Berlawanan arah — satu kurang (-), satu lebih (+) — TP 1-→TP 1+",
    "Melibatkan TP 3": "Off-taste (TP 3) — Pass→TP 3, TP 1-→TP 3",
}


def render(df: pd.DataFrame) -> None:
    """Render Tab 2 — Gap Analysis."""
    st.subheader("Gap Analysis — KimFis vs Verifikator")

    df_verif = df[df["Comparison"].isin(["MATCH", "MISMATCH"])].copy()
    df_mm    = df[df["Comparison"] == "MISMATCH"].copy()
    total_mm = len(df_mm)
    total_vf = len(df_verif)
    gap_rate = total_mm / total_vf * 100 if total_vf else 0

    if df_mm.empty:
        st.info("Tidak ada mismatch pada filter yang dipilih.")
        return

    # ── Pengantar storytelling dari Tab 1 ────────────────────────
    st.markdown(
        f"""
        <div style="background:#f8f9fa; border-left:4px solid #185FA5;
                    border-radius:8px; padding:14px 18px; margin-bottom:16px;
                    font-size:14px; color:#1a1a1a; line-height:1.8;">
        Di Tab Overview terlihat gap rate
        <b style="color:#D32F2F">{gap_rate:.1f}%</b>
        dari <b>{total_vf:,}</b> sampel terverifikasi
        (<b>{total_mm:,}</b> kejadian gap).
        &nbsp; Tab ini menjawab:
        <b>tipe gap apa yang dominan?</b> &nbsp;·&nbsp;
        <b>trennya membaik atau memburuk?</b> &nbsp;·&nbsp;
        <b>produk dan shift mana yang paling banyak gap?</b>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Section 1: Tipe Gap + Heatmap ────────────────────────────
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Distribusi Tipe Gap")
        _render_gap_type(df_mm, total_mm)

    with col_b:
        st.subheader("Heatmap KimFis × Verifikator")
        st.caption(
            "Warna menunjukkan jarak gap — 🟢 match, "
            "🟡 beda 1 level, 🟠 beda 2 level, 🔴 beda 3+. "
            "Angka = jumlah kejadian."
        )
        _render_heatmap(df)

    st.divider()

    # ── Section 2: Trend Gap Rate % Bulanan ──────────────────────
    st.subheader("Trend Gap Rate per Bulan")
    st.caption(
        "Gap rate % = mismatch ÷ total terverifikasi per bulan. "
        "Lebih informatif dari volume karena memperhitungkan "
        "perbedaan jumlah sampel tiap bulan."
    )
    _render_trend_rate(df)

    st.divider()

    # ── Section 3: Breakdown per Produk + Shift ───────────────────
    col_c, col_d = st.columns(2)
    with col_c:
        st.subheader("Breakdown Gap per Produk")
        st.caption("Top 10 produk — tipe gap apa yang dominan.")
        _render_breakdown_produk(df_mm)

    with col_d:
        st.subheader("Breakdown Gap per Shift")
        st.caption("Gap rate % per shift — shift mana yang paling tinggi gapnya.")
        _render_breakdown_shift(df_mm, df_verif)

    st.divider()

    # ── Section 4: Gap Breakdown Detail ─────────────────────────
    st.subheader("📋 Detail Breakdown per Kategori Gap")
    _render_gap_breakdown(df_mm, total_mm)

    st.divider()

    # ── Section 5: Gap Berbahaya (expander) ──────────────────────
    with st.expander("🚨 Gap Berbahaya — klik untuk lihat detail"):
        st.caption(
            "Gap berbahaya mencakup tiga kondisi: "
            "(1) salah satu pihak menilai TP 3 — apapun penilaian pihak lainnya, "
            "(2) salah satu pihak menilai TP 2 — apapun penilaian pihak lainnya "
            "(TP 2 memicu Triangle Test, jadi gap di level ini berdampak langsung "
            "ke keputusan release), "
            "(3) Beda Arah murni TP 1 (TP 1- vs TP 1+) — beda persepsi dasar. "
            "Gap Pass↔TP 1 satu arah dianggap wajar dan tidak termasuk di sini. "
            "Setiap kejadian perlu ditelusuri apakah ada justifikasi atau catatan release."
        )
        _render_dangerous_gap(df)

    st.divider()

    # ── Section 6: Sankey (visual summary, collapsible) ──────────
    with st.expander("🔀 Sankey — Aliran status KimFis → Verifikator"):
        st.caption(
            "Diagram aliran dari penilaian KimFis (kiri) ke Verifikator (kanan). "
            "Hijau = match, merah = gap."
        )
        _render_sankey(df)


# ── Sub-renderers ────────────────────────────────────────────────

def _render_gap_type(df_mm: pd.DataFrame, total_mm: int) -> None:
    """Bar chart horizontal tipe gap."""
    # Klasifikasi ulang dari KF_Status dan Verif_Status
    df_mm = df_mm.copy()
    df_mm["Kategori"] = df_mm.apply(
        lambda r: classify_gap(r["KF_Status"], r["Verif_Status"]), axis=1
    )
    cat_df = (
        df_mm["Kategori"].value_counts()
        .reindex(CAT_ORDER).dropna()
        .reset_index()
    )
    cat_df.columns = ["Kategori", "Jumlah"]
    cat_df["% Gap"] = (cat_df["Jumlah"] / total_mm * 100).round(1)
    cat_df["Label"] = cat_df.apply(
        lambda r: f"{r['Jumlah']:,}  ({r['% Gap']}%)", axis=1
    )
    cat_df["Icon"] = cat_df["Kategori"].map(CAT_ICONS)
    cat_df["Label_Y"] = cat_df.apply(
        lambda r: f"{r['Icon']} {r['Kategori']}", axis=1
    )
    cat_df["Color"] = cat_df["Kategori"].map(CAT_COLORS)

    fig = go.Figure()
    for _, row in cat_df.iterrows():
        fig.add_trace(go.Bar(
            x=[row["Jumlah"]], y=[row["Label_Y"]],
            orientation="h",
            text=[row["Label"]],
            textposition="inside",
            insidetextanchor="middle",
            marker_color=row["Color"],
            name=row["Kategori"],
            showlegend=False,
        ))
    fig.update_layout(
        template="plotly_white", height=200,
        margin=dict(t=10, b=10, l=10, r=10),
        xaxis_title="Jumlah Kejadian", yaxis_title="",
        barmode="stack",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Mini legend + deskripsi
    for cat in CAT_ORDER:
        row = cat_df[cat_df["Kategori"] == cat]
        if not row.empty:
            st.caption(f"{CAT_ICONS[cat]} **{cat}** — {CAT_DESC[cat]}")

    # Insight box dari engine
    render_insight_box(gen_insight_gap_type(df_mm, total_mm), context="gap_type")


def _render_heatmap(df: pd.DataFrame) -> None:
    """Heatmap dengan warna berdasarkan jarak gap."""
    import numpy as np

    heat_df = (
        df[df["Comparison"].isin(["MATCH", "MISMATCH"])]
        .groupby(["KF_Status", "Verif_Status"]).size().reset_index(name="Jumlah")
    )
    heat_pivot = heat_df.pivot_table(
        index="KF_Status", columns="Verif_Status",
        values="Jumlah", fill_value=0
    )
    vr = [s for s in STATUS_ORDER if s in heat_pivot.index]
    vc = [s for s in STATUS_ORDER if s in heat_pivot.columns]
    heat_pivot = heat_pivot.loc[vr, vc]

    z_arr = np.array([
        [abs(STATUS_NUM.get(r, 0) - STATUS_NUM.get(c, 0)) for c in vc]
        for r in vr
    ], dtype=float)
    text_mat = [
        [str(int(heat_pivot.loc[r, c])) if heat_pivot.loc[r, c] > 0 else ""
         for c in vc]
        for r in vr
    ]
    colorscale = [
        [0.00, "rgba(46,139,87,0.25)"],
        [0.20, "rgba(255,220,50,0.35)"],
        [0.45, "rgba(230,120,0,0.50)"],
        [0.70, "rgba(211,47,47,0.60)"],
        [1.00, "rgba(139,0,0,0.75)"],
    ]
    fig = go.Figure(go.Heatmap(
        z=z_arr, x=vc, y=vr,
        text=text_mat, texttemplate="%{text}",
        textfont=dict(size=13, color="black"),
        colorscale=colorscale, zmin=0, zmax=4,
        showscale=False, xgap=2, ygap=2,
    ))
    fig.update_layout(
        margin=dict(t=10, b=50, l=10, r=10),
        xaxis_title="Status Verifikator",
        yaxis_title="Status KimFis",
        template="plotly_white", height=320,
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_trend_rate(df: pd.DataFrame) -> None:
    """Trend gap RATE % bulanan — bukan volume."""
    dft = df[df["Comparison"].isin(["MATCH", "MISMATCH"])].copy()
    dft["Month"] = pd.to_datetime(dft["Date"], errors="coerce").dt.to_period("M").astype(str)

    monthly = (
        dft.groupby("Month")
        .agg(
            Total=("Comparison", "count"),
            Mismatch=("Comparison", lambda x: (x == "MISMATCH").sum()),
        )
        .reset_index()
    )
    monthly["Gap Rate %"] = (monthly["Mismatch"] / monthly["Total"] * 100).round(1)
    monthly["Match Rate %"] = 100 - monthly["Gap Rate %"]

    # Line chart gap rate + bar volume sebagai konteks
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=monthly["Month"], y=monthly["Total"],
        name="Total Terverifikasi",
        marker_color="rgba(24,95,165,0.2)",
        yaxis="y2",
    ))
    fig.add_trace(go.Scatter(
        x=monthly["Month"], y=monthly["Gap Rate %"],
        name="Gap Rate %",
        mode="lines+markers+text",
        line=dict(color="#D32F2F", width=2.5),
        marker=dict(size=8, color="#D32F2F"),
        text=monthly["Gap Rate %"].apply(lambda x: f"{x}%"),
        textposition="top center",
        textfont=dict(size=11),
    ))
    fig.update_layout(
        template="plotly_white", height=380,
        margin=dict(t=20, b=40, l=10, r=10),
        legend=dict(orientation="h", y=1.1),
        xaxis=dict(title="", tickangle=-45),
        yaxis=dict(title="Gap Rate (%)", range=[0, 100]),
        yaxis2=dict(
            title="Total Sampel Terverifikasi",
            overlaying="y", side="right",
            showgrid=False,
        ),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Highlight bulan terburuk dan terbaik
    if len(monthly) >= 2:
        worst = monthly.loc[monthly["Gap Rate %"].idxmax()]
        best  = monthly.loc[monthly["Gap Rate %"].idxmin()]
        col1, col2 = st.columns(2)
        col1.metric(
            "📈 Bulan Terburuk",
            f"{worst['Month']}",
            f"{worst['Gap Rate %']}% gap rate ({int(worst['Mismatch'])} gap)",
            delta_color="inverse",
        )
        col2.metric(
            "📉 Bulan Terbaik",
            f"{best['Month']}",
            f"{best['Gap Rate %']}% gap rate ({int(best['Mismatch'])} gap)",
        )

    # Insight box dari engine
    render_insight_box(gen_insight_trend(monthly), context="trend")


def _render_breakdown_produk(df_mm: pd.DataFrame) -> None:
    """Stacked bar top 10 produk per kategori gap."""
    df_mm = df_mm.copy()
    df_mm["Kategori"] = df_mm.apply(
        lambda r: classify_gap(r["KF_Status"], r["Verif_Status"]) or "Lainnya", axis=1
    )
    tpg = df_mm.groupby(["Product_Name", "Kategori"]).size().reset_index(name="Jumlah")
    top10 = (
        tpg.groupby("Product_Name")["Jumlah"].sum()
        .nlargest(10).index.tolist()
    )
    tpg = tpg[tpg["Product_Name"].isin(top10)]
    fig = px.bar(
        tpg, x="Jumlah", y="Product_Name", color="Kategori",
        orientation="h", barmode="stack",
        color_discrete_map=CAT_COLORS,
        category_orders={"Kategori": CAT_ORDER},
        template="plotly_white", height=380,
        labels={"Product_Name": "Produk", "Jumlah": "Jumlah Gap"},
    )
    fig.update_layout(
        legend=dict(orientation="h", y=-0.3),
        yaxis={"categoryorder": "total ascending"},
        margin=dict(t=10, b=80, l=10, r=10),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_breakdown_shift(df_mm: pd.DataFrame, df_verif: pd.DataFrame) -> None:
    """Gap rate % per shift — SUMMARY level. Detail ada di Tab 4."""
    def norm_shift(v):
        s = str(v).strip()
        try:
            f = float(s)
            if f == int(f): return str(int(f))
        except: pass
        return s

    df_mm    = df_mm.copy()
    df_verif = df_verif.copy()
    df_mm["Shift_Label"]    = df_mm["Shift_Code"].apply(norm_shift)
    df_verif["Shift_Label"] = df_verif["Shift_Code"].apply(norm_shift)

    sh_total = df_verif.groupby("Shift_Label").size().reset_index(name="Total")
    sh_mm    = df_mm.groupby("Shift_Label").size().reset_index(name="Mismatch")
    sh_rate  = sh_total.merge(sh_mm, on="Shift_Label", how="left").fillna(0)
    sh_rate["Gap Rate %"] = (sh_rate["Mismatch"] / sh_rate["Total"] * 100).round(1)
    sh_rate["Label"] = sh_rate.apply(
        lambda r: f"{r['Gap Rate %']}%  ({int(r['Mismatch'])} gap)", axis=1
    )

    # Warna: merah untuk tertinggi, biru untuk lainnya
    max_rate = sh_rate["Gap Rate %"].max()
    sh_rate["Color"] = sh_rate["Gap Rate %"].apply(
        lambda x: "#D32F2F" if x == max_rate else "#185FA5"
    )

    fig = go.Figure()
    for _, row in sh_rate.iterrows():
        fig.add_trace(go.Bar(
            x=[row["Shift_Label"]], y=[row["Gap Rate %"]],
            text=[row["Label"]],
            textposition="outside",
            marker_color=row["Color"],
            showlegend=False,
            name=row["Shift_Label"],
        ))

    fig.update_layout(
        template="plotly_white", height=320,
        margin=dict(t=20, b=40, l=10, r=10),
        xaxis=dict(
            title="Shift",
            categoryorder="array",
            categoryarray=["1","1-2","2","2-3","3"],
        ),
        yaxis=dict(title="Gap Rate (%)", range=[0, 60]),
        barmode="group",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Highlight shift terburuk
    worst = sh_rate.loc[sh_rate["Gap Rate %"].idxmax()]
    st.caption(
        f"🔴 Shift **{worst['Shift_Label']}** memiliki gap rate tertinggi "
        f"**{worst['Gap Rate %']}%** ({int(worst['Mismatch'])} dari {int(worst['Total'])} sampel). "
        f"→ Detail investigasi per analis tersedia di **Tab 🏭 Shift & Analis**."
    )


def _render_gap_breakdown(df_mm: pd.DataFrame, total_mm: int) -> None:
    """Detail breakdown per kategori gap."""
    gap_rows = [
        {"Kategori": classify_gap(r["KF_Status"], r["Verif_Status"]),
         "Gap Type": r.get("Gap_Type", "")}
        for _, r in df_mm.iterrows()
        if classify_gap(r["KF_Status"], r["Verif_Status"])
    ]
    if not gap_rows:
        return

    gdf    = pd.DataFrame(gap_rows)
    cats   = gdf.groupby("Kategori").size().reset_index(name="Jumlah")
    cats["% Mismatch"] = (cats["Jumlah"] / total_mm * 100).round(1)
    detail = (gdf.groupby(["Kategori", "Gap Type"]).size()
              .reset_index(name="Jumlah"))
    detail["% Mismatch"] = (detail["Jumlah"] / total_mm * 100).round(1)

    cats["_ord"] = cats["Kategori"].map({c: i for i, c in enumerate(CAT_ORDER)})
    cats = cats.sort_values("_ord").drop(columns="_ord")

    st.caption(f"Total: **{len(gap_rows):,}** gap terklasifikasi dari {total_mm:,} mismatch")
    for _, row in cats.iterrows():
        cat = row["Kategori"]
        st.markdown(
            f"{CAT_ICONS.get(cat, '•')} **{cat}** — "
            f"{row['Jumlah']:,} ({row['% Mismatch']}%)  \n"
            f"<span style='font-size:12px;color:#888'>{CAT_DESC.get(cat, '')}</span>",
            unsafe_allow_html=True,
        )
        sub = detail[detail["Kategori"] == cat][["Gap Type", "Jumlah", "% Mismatch"]]
        sub = sub.sort_values("Jumlah", ascending=False).reset_index(drop=True)
        sub.index += 1
        st.dataframe(sub, use_container_width=True, height=160)
        st.markdown("")


def _render_dangerous_gap(df: pd.DataFrame) -> None:
    """
    Gap berbahaya — tiga kondisi (business rule):
    1. Melibatkan TP 3 (apapun pasangannya) — off-taste, paling kritis
    2. Melibatkan TP 2 (apapun pasangannya) — Pass↔TP2, TP1↔TP2, TP2↔TP2 lawan arah
       TP 2 sendiri sudah memicu Triangle Test, jadi gap di level ini
       punya konsekuensi keputusan release yang nyata
    3. Beda Arah murni TP 1 (TP 1- ↔ TP 1+) — beda persepsi dasar tanpa TP2/TP3
    Gap yang TIDAK termasuk berbahaya: Pass ↔ TP 1 (satu arah) — Beda Tingkatan biasa.
    """
    TP2_SET = {"TP 2-", "TP 2+"}
    TP1_SET = {"TP 1-", "TP 1+"}

    dv = df[df["Verif_Status"].notna() & df["KF_Status"].notna()].copy()
    dv = dv[dv["KF_Status"] != dv["Verif_Status"]].copy()

    # Kondisi 1: salah satu TP 3
    mask_tp3 = (dv["KF_Status"] == "TP 3") | (dv["Verif_Status"] == "TP 3")

    # Kondisi 2: salah satu TP 2 (apapun pasangannya)
    mask_tp2 = dv["KF_Status"].isin(TP2_SET) | dv["Verif_Status"].isin(TP2_SET)

    # Kondisi 3: Beda Arah murni TP 1 (tanpa TP2/TP3 — sudah ditangani di atas)
    mask_beda_arah_tp1 = (
        dv["KF_Status"].isin(TP1_SET) & dv["Verif_Status"].isin(TP1_SET) &
        (dv["KF_Status"] != dv["Verif_Status"])
    )

    danger = dv[mask_tp3 | mask_tp2 | mask_beda_arah_tp1].copy()
    danger["Gap_Type"] = danger["KF_Status"] + " → " + danger["Verif_Status"]

    def tag_bahaya(row):
        if row["KF_Status"] == "TP 3" or row["Verif_Status"] == "TP 3":
            return "Melibatkan TP 3"
        if row["KF_Status"] in TP2_SET or row["Verif_Status"] in TP2_SET:
            return "Melibatkan TP 2"
        return "Beda Arah TP 1"
    danger["Tipe Bahaya"] = danger.apply(tag_bahaya, axis=1)

    if danger.empty:
        st.success("✅ Tidak ada gap berbahaya pada periode ini.")
        return

    total_danger = len(danger)
    n_tp3   = (danger["Tipe Bahaya"] == "Melibatkan TP 3").sum()
    n_tp2   = (danger["Tipe Bahaya"] == "Melibatkan TP 2").sum()
    n_arah1 = (danger["Tipe Bahaya"] == "Beda Arah TP 1").sum()
    n_verif = df["Verif_Status"].notna().sum()
    pct     = round(total_danger / n_verif * 100, 1) if n_verif else 0

    st.error(
        f"🚨 **{total_danger:,} gap berbahaya** ({pct}% dari sampel terverifikasi). "
        f"Melibatkan TP 3: **{n_tp3}** · "
        f"Melibatkan TP 2: **{n_tp2}** · "
        f"Beda Arah TP 1: **{n_arah1}**. "
        f"Setiap kejadian perlu ditelusuri."
    )

    col_a, col_b = st.columns(2)

    with col_a:
        st.caption("**Tipe gap berbahaya terbanyak**")
        gt = (danger.groupby(["Gap_Type","Tipe Bahaya"]).size()
              .reset_index(name="Jumlah")
              .sort_values("Jumlah", ascending=False)
              .head(8))
        gt["% dari Total"] = (gt["Jumlah"] / total_danger * 100).round(1)
        gt.index = range(1, len(gt) + 1)
        st.dataframe(gt, use_container_width=True, hide_index=False, height=260)

    with col_b:
        st.caption("**Produk dengan gap berbahaya terbanyak**")
        pp = (danger.groupby("Product_Name").size()
              .reset_index(name="Jumlah")
              .sort_values("Jumlah", ascending=False)
              .head(8))
        pp["% dari Total"] = (pp["Jumlah"] / total_danger * 100).round(1)
        pp.index = range(1, len(pp) + 1)
        st.dataframe(pp, use_container_width=True, hide_index=False, height=260)


def _render_sankey(df: pd.DataFrame) -> None:
    """Sankey diagram aliran status KimFis → Verifikator."""
    sdf = (
        df[df["Comparison"].isin(["MATCH", "MISMATCH"])]
        .groupby(["KF_Status", "Verif_Status"]).size().reset_index(name="Jumlah")
    )
    kf_nodes  = [f"KF: {s}"    for s in STATUS_ORDER if s in sdf["KF_Status"].values]
    vf_nodes  = [f"Verif: {s}" for s in STATUS_ORDER if s in sdf["Verif_Status"].values]
    all_nodes = kf_nodes + vf_nodes
    node_colors = [STATUS_COLORS.get(n.split(": ", 1)[1], "#aaa") for n in all_nodes]

    src, tgt, val, lc = [], [], [], []
    for _, r in sdf.iterrows():
        s = f"KF: {r['KF_Status']}"
        t = f"Verif: {r['Verif_Status']}"
        if s in all_nodes and t in all_nodes:
            src.append(all_nodes.index(s))
            tgt.append(all_nodes.index(t))
            val.append(r["Jumlah"])
            lc.append("rgba(46,139,87,0.3)" if r["KF_Status"] == r["Verif_Status"]
                       else "rgba(211,47,47,0.25)")

    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(
            pad=20, thickness=25,
            line=dict(color="white", width=0.5),
            label=all_nodes, color=node_colors,
        ),
        link=dict(source=src, target=tgt, value=val, color=lc),
    ))
    fig.update_layout(
        height=420, margin=dict(t=10, b=10, l=20, r=20),
        template="plotly_white",
    )
    st.plotly_chart(fig, use_container_width=True)